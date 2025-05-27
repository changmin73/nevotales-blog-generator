from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import tempfile
import os
import urllib.request
from urllib.parse import urljoin, urlparse
import random
from datetime import datetime
import re
from PIL import Image, ImageFilter, ImageEnhance
from io import BytesIO
import base64
import json

app = Flask(__name__)

# =============================================================================
# 기본 유틸리티 함수들
# =============================================================================

def is_accessible_url(url):
    """URL 접근 가능성 체크"""
    try:
        response = requests.head(url, timeout=5, 
                                headers={'User-Agent': 'Mozilla/5.0 (compatible; TravelBot/1.0)'})
        return response.status_code == 200
    except:
        return True

def detect_language(text):
    """간단한 언어 감지"""
    english_words = ['the', 'and', 'is', 'in', 'to', 'of', 'a', 'for', 'with', 'on', 'that', 'this']
    korean_chars = len([c for c in text if '\uAC00' <= c <= '\uD7A3'])
    english_word_count = len([word for word in text.lower().split()[:50] if word in english_words])
    
    if korean_chars > 10:
        return "ko"
    elif english_word_count > 3:
        return "en"
    else:
        return "other"

def translate_text(text):
    """번역 함수 (현재는 원본 반환)"""
    return text

# =============================================================================
# 블로그 콘텐츠 수집기
# =============================================================================

def download_and_process_blog(url, keyword):
    """블로그 처리"""
    print(f"🔍 처리 중: {url}")
    
    if not is_accessible_url(url):
        return {"error": "URL not accessible", "url": url}

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        res = requests.get(url, timeout=15, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")

        # 텍스트 추출
        paragraphs = soup.find_all("p")
        text_content = " ".join([p.get_text(strip=True) for p in paragraphs])
        
        if len(text_content) < 100:
            return {"error": "Text too short", "url": url}
        
        # 언어 감지
        language = detect_language(text_content)
        print(f"🔤 감지된 언어: {language}")
        
        # 번역 (영어면 그대로 유지)
        if language == "en":
            translated_text = text_content[:1000]
        else:
            translated_text = translate_text(text_content[:1000])
        
        # 결과 준비
        result_json = {
            "title": soup.title.string.strip() if soup.title and soup.title.string else "No Title",
            "summary_original": text_content[:1000],
            "summary_translated": translated_text,
            "language": language,
            "url": url,
            "processed_at": datetime.utcnow().isoformat(),
            "text_length": len(text_content)
        }
        
        print(f"✅ 성공: {result_json['title'][:50]}... (언어: {language})")
        return result_json
        
    except Exception as e:
        print(f"❌ 오류: {url} - {e}")
        return {"error": str(e), "url": url}

# =============================================================================
# 안전한 이미지 처리기
# =============================================================================

def smart_image_downloader(soup, base_url, min_size=150):
    """고품질 이미지만 선별해서 다운로드"""
    
    downloaded_images = []
    temp_dir = tempfile.mkdtemp()
    
    print(f"🖼️ 이미지 수집 시작... (최소 크기: {min_size}px)")
    
    img_tags = soup.find_all('img')
    print(f"📊 총 {len(img_tags)}개의 이미지 태그 발견")
    
    valid_images = 0
    
    for i, img in enumerate(img_tags[:15]):
        try:
            img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            
            if not img_url:
                continue
                
            # 상대 경로를 절대 경로로 변환
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            elif img_url.startswith('/'):
                img_url = urljoin(base_url, img_url)
            elif not img_url.startswith('http'):
                img_url = urljoin(base_url, img_url)
            
            # 파일 확장자 확인
            parsed_url = urlparse(img_url)
            if not any(parsed_url.path.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                continue
            
            # 이미지 다운로드
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            req = urllib.request.Request(img_url, headers=headers)
            
            with urllib.request.urlopen(req, timeout=10) as response:
                img_data = response.read()
            
            # 이미지 크기 확인
            try:
                with Image.open(BytesIO(img_data)) as pil_img:
                    width, height = pil_img.size
                    
                    if width < min_size or height < min_size:
                        continue
                    
                    # 이상한 비율 제외
                    ratio = max(width, height) / min(width, height)
                    if ratio > 4:
                        continue
                    
                    # 파일 저장
                    filename = f"image_{valid_images+1}_{width}x{height}.jpg"
                    filepath = os.path.join(temp_dir, filename)
                    
                    # JPEG로 변환해서 저장
                    if pil_img.mode in ('RGBA', 'LA', 'P'):
                        pil_img = pil_img.convert('RGB')
                    
                    pil_img.save(filepath, 'JPEG', quality=85)
                    
                    downloaded_images.append({
                        'original_url': img_url,
                        'local_path': filepath,
                        'filename': filename,
                        'size': (width, height),
                        'file_size': len(img_data)
                    })
                    
                    valid_images += 1
                    print(f"✅ 저장됨: {filename} ({width}x{height})")
                    
                    if valid_images >= 5:  # 최대 5개만
                        break
                    
            except Exception as img_error:
                continue
                
        except Exception as e:
            continue
    
    print(f"🎉 총 {valid_images}개의 고품질 이미지 수집 완료!")
    return downloaded_images, temp_dir

def disguise_image(image_path, output_path):
    """이미지를 알아볼 수 없게 변조"""
    
    try:
        with Image.open(image_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 크기 변경
            width, height = img.size
            scale_factor = random.uniform(0.8, 1.2)
            new_size = (int(width * scale_factor), int(height * scale_factor))
            img = img.resize(new_size, Image.LANCZOS)
            
            # 밝기 조정
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(random.uniform(0.8, 1.2))
            
            # 대비 조정
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(random.uniform(0.8, 1.2))
            
            # 색상 조정
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(random.uniform(0.9, 1.1))
            
            # 경미한 블러 효과
            if random.choice([True, False]):
                img = img.filter(ImageFilter.GaussianBlur(radius=0.3))
            
            # 좌우 반전 (50% 확률)
            if random.choice([True, False]):
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            
            # 품질 저하 (메타데이터 제거)
            img.save(output_path, 'JPEG', quality=random.randint(75, 90), optimize=True)
            
            return True
            
    except Exception as e:
        print(f"❌ 이미지 변조 오류: {e}")
        return False

def safe_image_processor(soup, base_url, keyword, min_size=150):
    """안전한 이미지 처리 (변조 포함)"""
    
    print("🛡️ 안전한 이미지 수집 모드...")
    
    # 기본 이미지 다운로드
    original_images, temp_dir = smart_image_downloader(soup, base_url, min_size)
    
    if not original_images:
        return [], None
    
    # 변조된 이미지 저장 폴더
    disguised_dir = tempfile.mkdtemp(prefix="disguised_")
    disguised_images = []
    
    print(f"🎭 {len(original_images)}개 이미지 변조 중...")
    
    for i, img_info in enumerate(original_images):
        try:
            original_path = img_info['local_path']
            
            # 새 파일명 생성
            new_filename = f"{keyword}_{random.randint(1000,9999)}_{i+1}.jpg"
            disguised_path = os.path.join(disguised_dir, new_filename)
            
            # 이미지 변조
            if disguise_image(original_path, disguised_path):
                disguised_images.append({
                    'original_url': img_info['original_url'],
                    'disguised_path': disguised_path,
                    'new_filename': new_filename,
                    'original_size': img_info['size']
                })
                print(f"✅ 변조 완료: {new_filename}")
                
        except Exception as e:
            continue
    
    print(f"🎉 {len(disguised_images)}개 이미지 안전하게 변조 완료!")
    return disguised_images, disguised_dir

# =============================================================================
# 멀티 블로그 프로세서
# =============================================================================

def multi_blog_processor(urls, keyword="travel", max_blogs=3):
    """여러 블로그를 동시에 처리해서 콘텐츠 수집"""
    
    print(f"🌍 {len(urls[:max_blogs])}개 블로그 동시 처리 시작...")
    print(f"🎯 키워드: {keyword}")
    
    all_results = []
    all_images = []
    
    for i, url in enumerate(urls[:max_blogs]):
        print(f"\n📖 블로그 {i+1}/{min(len(urls), max_blogs)}: {url}")
        
        try:
            # 텍스트 크롤링
            blog_result = download_and_process_blog(url, keyword)
            
            if "error" not in blog_result:
                print(f"✅ 텍스트 수집 성공: {blog_result.get('title', 'No title')[:50]}...")
                
                # 이미지 크롤링
                response = requests.get(url, timeout=10, 
                                      headers={'User-Agent': 'Mozilla/5.0 (compatible; TravelBot/1.0)'})
                soup = BeautifulSoup(response.text, 'html.parser')
                
                images, temp_dir = safe_image_processor(soup, url, keyword.replace(" ", "_"), min_size=150)
                
                # 결과에 이미지 정보 추가
                blog_result['images_info'] = {
                    'count': len(images),
                    'images': images,
                    'temp_dir': temp_dir
                }
                
                all_results.append(blog_result)
                all_images.extend(images)
                
                print(f"📸 이미지 {len(images)}개 추가 수집")
                
            else:
                print(f"❌ 실패: {blog_result.get('error')}")
                
        except Exception as e:
            print(f"❌ 오류: {e}")
            continue
    
    print(f"\n🎊 전체 결과:")
    print(f"- 성공한 블로그: {len(all_results)}개")
    print(f"- 총 수집 이미지: {len(all_images)}개")
    print(f"- 총 텍스트 길이: {sum(len(r.get('summary_original', '')) for r in all_results)}자")
    
    return all_results, all_images

# =============================================================================
# 강화된 콘텐츠 믹서
# =============================================================================

def enhanced_content_mixer(blog_results, target_keyword, target_location="Tokyo"):
    """더 길고 자세한 글을 생성하는 강화된 믹서"""
    
    print(f"📝 Enhanced Content Mixer 시작...")
    print(f"🎯 타겟 키워드: {target_keyword}")
    print(f"🗺️ 타겟 위치: {target_location}")
    
    if not blog_results:
        return {"error": "No blog content to mix"}
    
    # 모든 텍스트 대량 수집
    all_texts = []
    for result in blog_results:
        if result.get('summary_original'):
            all_texts.append(result['summary_original'])
        if result.get('summary_translated'):
            all_texts.append(result['summary_translated'])
    
    # 더 세밀한 문장 분리
    sentences = []
    for text in all_texts:
        text_sentences = re.split(r'[.!?]\s+', text)
        valid_sentences = [s.strip() + '.' for s in text_sentences if len(s.strip()) > 10]
        sentences.extend(valid_sentences)
    
    print(f"📊 수집된 문장: {len(sentences)}개")
    
    # 문장 분류
    random.shuffle(sentences)
    
    travel_sentences = [s for s in sentences if any(word in s.lower() for word in ['travel', 'trip', 'visit', 'go', 'see'])]
    place_sentences = [s for s in sentences if any(word in s.lower() for word in ['place', 'city', 'area', 'location', 'spot'])]
    experience_sentences = [s for s in sentences if any(word in s.lower() for word in ['experience', 'amazing', 'beautiful', 'great', 'wonderful'])]
    food_sentences = [s for s in sentences if any(word in s.lower() for word in ['food', 'eat', 'restaurant', 'delicious', 'taste'])]
    culture_sentences = [s for s in sentences if any(word in s.lower() for word in ['culture', 'local', 'people', 'traditional', 'history'])]
    other_sentences = [s for s in sentences if s not in travel_sentences + place_sentences + experience_sentences + food_sentences + culture_sentences]
    
    # 대폭 확장된 글 구조
    mixed_content = {
        "title": f"My Complete Guide to {target_keyword} in {target_location}: An Unforgettable Adventure",
        "introduction": f"Planning a {target_keyword} trip to {target_location}? After spending incredible time exploring this amazing destination, I'm excited to share my comprehensive experience with you. From hidden gems to must-visit spots, here's everything you need to know about {target_keyword} in {target_location}.",
        "body_paragraphs": [],
        "conclusion": f"My {target_keyword} journey in {target_location} exceeded all expectations. Whether you're a first-time visitor or returning traveler, {target_location} offers endless opportunities for {target_keyword} adventures. I can't wait to return and discover even more!",
        "seo_keywords": [target_keyword, target_location, "travel guide", "things to do", "best places"],
        "word_count": 0
    }
    
    # 대폭 확장된 단락들
    expanded_paragraphs = [
        {
            "heading": f"Why {target_location} is Perfect for {target_keyword}",
            "sentences": travel_sentences[:4] + experience_sentences[:3],
            "filler": f"When I first arrived in {target_location}, I immediately understood why it's considered one of the world's top {target_keyword} destinations."
        },
        {
            "heading": f"Best Time to Visit {target_location} for {target_keyword}",
            "sentences": other_sentences[:3] + travel_sentences[4:7],
            "filler": f"Timing your {target_keyword} trip to {target_location} can make all the difference in your experience."
        },
        {
            "heading": f"Top {target_keyword} Destinations in {target_location}",
            "sentences": place_sentences[:5] + experience_sentences[3:6],
            "filler": f"After exploring numerous locations, these are my absolute favorite {target_keyword} spots in {target_location}."
        },
        {
            "heading": f"Local Culture and {target_keyword} Traditions",
            "sentences": culture_sentences[:4] + other_sentences[3:6],
            "filler": f"Understanding local culture enhanced my {target_keyword} experience in {target_location} tremendously."
        },
        {
            "heading": f"Food and Dining During Your {target_keyword} Trip",
            "sentences": food_sentences[:4] + experience_sentences[6:8],
            "filler": f"No {target_keyword} trip to {target_location} is complete without experiencing the incredible local cuisine."
        }
    ]
    
    total_words = 0
    
    for para in expanded_paragraphs:
        if para["sentences"]:
            para_content = para["filler"] + " "
            
            sentence_content = " ".join(para["sentences"][:4])
            # 1인칭 변환
            sentence_content = sentence_content.replace(" you ", " I ").replace(" You ", " I ")
            sentence_content = sentence_content.replace(" your ", " my ").replace(" Your ", " My ")
            sentence_content = sentence_content.replace("you're", "I'm").replace("You're", "I'm")
            
            full_content = para_content + sentence_content
            
            mixed_content["body_paragraphs"].append({
                "heading": para["heading"],
                "content": full_content
            })
            
            total_words += len(full_content.split())
    
    mixed_content["word_count"] = total_words
    
    return mixed_content

# =============================================================================
# WordPress 자동 포스터 (간단 버전)
# =============================================================================

class WordPressAutoPoster:
    def __init__(self, site_url, username, app_password):
        self.site_url = site_url.rstrip('/')
        self.username = username
        self.app_password = app_password
        self.api_url = f"{self.site_url}/wp-json/wp/v2"
        
        # 인증 헤더 생성
        credentials = f"{username}:{app_password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        self.headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
    
    def create_post(self, title, content, status='publish'):
        """워드프레스에 글 작성 (간단 버전)"""
        
        post_data = {
            'title': title,
            'content': content,
            'status': status,
            'format': 'standard'
        }
        
        try:
            posts_url = f"{self.api_url}/posts"
            response = requests.post(posts_url, headers=self.headers, json=post_data)
            
            if response.status_code == 201:
                post_data = response.json()
                print(f"✅ 글 작성 성공!")
                print(f"📝 제목: {post_data['title']['rendered']}")
                print(f"🔗 URL: {post_data['link']}")
                
                return {
                    'id': post_data['id'],
                    'title': post_data['title']['rendered'],
                    'url': post_data['link'],
                    'status': post_data['status']
                }
            else:
                print(f"❌ 글 작성 실패: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ 글 작성 오류: {e}")
            return None

# =============================================================================
# 통합 시스템
# =============================================================================

def complete_blog_generation_system(target_urls, keyword, location):
    """완전한 블로그 생성 시스템"""
    
    print("🚀 Complete Blog Generation System 시작!")
    print(f"🎯 키워드: {keyword}")
    print(f"🗺️ 위치: {location}")
    print(f"📚 대상 URL 수: {len(target_urls)}")
    
    # 1. 멀티 블로그 처리
    print("\n" + "="*50)
    print("1️⃣ 멀티 블로그 콘텐츠 수집")
    print("="*50)
    
    blog_results, collected_images = multi_blog_processor(target_urls, keyword, max_blogs=3)
    
    if not blog_results:
        return {"error": "No blog content collected", "success": False}
    
    # 2. 콘텐츠 믹싱
    print("\n" + "="*50)
    print("2️⃣ 콘텐츠 믹싱 및 글 생성")
    print("="*50)
    
    final_article = enhanced_content_mixer(blog_results, keyword, location)
    
    # 3. 최종 결과
    print("\n" + "="*50)
    print("3️⃣ 최종 결과")
    print("="*50)
    
    final_result = {
        "article": final_article,
        "images": collected_images,
        "source_blogs": len(blog_results),
        "total_images": len(collected_images),
        "success": True
    }
    
    print(f"✅ 완료!")
    print(f"📝 생성된 글: {final_article.get('word_count', 0)}단어")
    print(f"📸 수집된 이미지: {len(collected_images)}개")
    print(f"📚 소스 블로그: {len(blog_results)}개")
    
    return final_result

# =============================================================================
# Flask 라우트들
# =============================================================================

@app.route('/', methods=['GET'])
def home():
    """홈페이지 - 서비스 상태 확인"""
    return jsonify({
        "service": "Nevotales Blog Generator",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "generate": "/generate-blog",
            "health": "/health"
        },
        "description": "Automated travel blog generation system for nevotales.com"
    })

@app.route('/health', methods=['GET'])
def health_check():
    """헬스 체크"""
    return jsonify({
        "status": "healthy", 
        "timestamp": datetime.utcnow().isoformat(),
        "service": "nevotales-blog-generator"
    })

@app.route('/generate-blog', methods=['POST', 'OPTIONS'])
def generate_blog():
    """Make.com에서 호출할 블로그 생성 엔드포인트"""
    
    # CORS 처리
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    try:
        # JSON 데이터 받기
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided", "success": False}), 400
        
        keyword = data.get('keyword', '').strip()
        location = data.get('location', 'Japan').strip()
        
        if not keyword:
            return jsonify({"error": "Keyword is required", "success": False}), 400
        
        print(f"🎯 Processing: {keyword} in {location}")
        
        # 여행 블로그 URL들
        travel_blog_urls = [
            "https://www.nomadicmatt.com/travel-blog/",
            "https://expertvagabond.com/",
            "https://www.adventurous-kate.com/",
            "https://www.theplanetd.com/",
            "https://migrationology.com/"
        ]
        
        # 1. 블로그 콘텐츠 생성
        result = complete_blog_generation_system(
            target_urls=travel_blog_urls,
            keyword=keyword,
            location=location
        )
        
        if not result.get("success"):
            return jsonify({
                "error": "Blog generation failed", 
                "keyword": keyword,
                "success": False
            }), 500
        
        # 2. WordPress 자동 포스팅 (환경변수에서 설정 읽기)
        wp_username = os.environ.get('WP_USERNAME')
        wp_app_password = os.environ.get('WP_APP_PASSWORD')
        
        if wp_username and wp_app_password:
            try:
                wp_poster = WordPressAutoPoster(
                    site_url="https://nevotales.com",
                    username=wp_username,
                    app_password=wp_app_password
                )
                
                # HTML 형식의 글 내용 생성
                html_content = f"<p>{result['article']['introduction']}</p>\n\n"
                
                for paragraph in result['article']['body_paragraphs']:
                    html_content += f"<h2>{paragraph['heading']}</h2>\n"
                    html_content += f"<p>{paragraph['content']}</p>\n\n"
                
                html_content += f"<h2>Conclusion</h2>\n"
                html_content += f"<p>{result['article']['conclusion']}</p>\n"
                
                wp_result = wp_poster.create_post(
                    title=result['article']['title'],
                    content=html_content,
                    status='publish'
                )
                
                if wp_result:
                    response_data = {
                        "success": True,
                        "keyword": keyword,
                        "location": location,
                        "wordpress_url": wp_result["url"],
                        "title": wp_result["title"],
                        "images_count": len(result["images"]),
                        "word_count": result["article"]["word_count"],
                        "timestamp": datetime.utcnow().isoformat()
                    }
                else:
                    response_data = {
                        "success": True,
                        "keyword": keyword,
                        "location": location,
                        "title": result["article"]["title"],
                        "images_count": len(result["images"]),
                        "word_count": result["article"]["word_count"],
                        "wordpress_error": "Failed to post to WordPress",
                        "timestamp": datetime.utcnow().isoformat()
                    }
            except Exception as wp_error:
                response_data = {
                    "success": True,
                    "keyword": keyword,
                    "location": location,
                    "title": result["article"]["title"],
                    "images_count": len(result["images"]),
                    "word_count": result["article"]["word_count"],
                    "wordpress_error": str(wp_error),
                    "timestamp": datetime.utcnow().isoformat()
                }
        else:
            # WordPress 설정이 없으면 글만 생성
            response_data = {
                "success": True,
                "keyword": keyword,
                "location": location,
                "title": result["article"]["title"],
                "images_count": len(result["images"]),
                "word_count": result["article"]["word_count"],
                "note": "WordPress credentials not configured",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        response = jsonify(response_data)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
        
    except Exception as e:
        error_response = jsonify({
            "error": str(e),
            "success": False,
            "timestamp": datetime.utcnow().isoformat()
        })
        error_response.headers.add('Access-Control-Allow-Origin', '*')
        return error_response, 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
