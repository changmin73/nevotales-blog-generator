# MoneyMaking_Crawler - Railway 배포용
import os
import requests
import json
import random
import tempfile
import re
from datetime import datetime
from urllib.parse import urlparse, urljoin
from io import BytesIO

from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from google.cloud import storage, translate_v3
from google.oauth2 import service_account
from langdetect import detect
from PIL import Image, ImageEnhance
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

app = Flask(__name__)

# 환경 변수에서 Google 서비스 계정 정보 가져오기
def get_google_credentials():
    try:
        service_account_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT')
        if service_account_json:
            service_account_info = json.loads(service_account_json)
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            return credentials
    except Exception as e:
        print(f"Google 인증 오류: {e}")
    return None

credentials = get_google_credentials()
if credentials:
    translate_client = translate_v3.TranslationServiceClient(credentials=credentials)
    storage_client = storage.Client(credentials=credentials)
    try:
        drive_service = build('drive', 'v3', credentials=credentials)
    except:
        drive_service = None
else:
    translate_client = None
    storage_client = None
    drive_service = None

# 타겟 블로그 URLs
TRAVEL_BLOG_URLS = [
    "https://www.nomadicmatt.com/travel-blog/",
    "https://expertvagabond.com/",
    "https://www.adventurous-kate.com/",
    "https://www.theplanetd.com/",
    "https://migrationology.com/",
    "https://www.backpackingfromtheheart.com/"
]

MIN_IMAGE_SIZE = 150

# 유틸리티 함수들
def is_accessible_url(url: str) -> bool:
    try:
        res = requests.head(url, timeout=5, allow_redirects=True)
        return res.status_code < 400
    except:
        return False

def translate_text(text: str, target_lang="en") -> str:
    if not translate_client or not credentials:
        return text
    try:
        parent = f"projects/{credentials.project_id}/locations/global"
        response = translate_client.translate_text(
            request={
                "parent": parent,
                "contents": [text],
                "mime_type": "text/plain",
                "source_language_code": "auto",
                "target_language_code": target_lang,
            }
        )
        return response.translations[0].translated_text
    except Exception as e:
        print(f"번역 오류: {e}")
        return text

def smart_image_downloader_with_disguise(soup, base_url, keyword, min_size=150):
    print(f"🖼️ 이미지 수집 + 변조 시작...")
    
    temp_dir = tempfile.mkdtemp()
    disguised_dir = tempfile.mkdtemp(prefix="disguised_")
    disguised_images = []
    
    img_tags = soup.find_all('img')[:10]
    valid_count = 0
    
    for i, img in enumerate(img_tags):
        try:
            img_url = img.get('src') or img.get('data-src')
            if not img_url:
                continue
                
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            elif img_url.startswith('/'):
                img_url = urljoin(base_url, img_url)
            elif not img_url.startswith('http'):
                img_url = urljoin(base_url, img_url)
            
            if not any(ext in img_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                continue
            
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            img_response = requests.get(img_url, headers=headers, timeout=10)
            
            if img_response.status_code != 200:
                continue
                
            img_data = img_response.content
            
            try:
                with Image.open(BytesIO(img_data)) as pil_img:
                    width, height = pil_img.size
                    
                    if width < min_size or height < min_size:
                        continue
                    
                    ratio = max(width, height) / min(width, height)
                    if ratio > 4:
                        continue
                    
                    if pil_img.mode != 'RGB':
                        pil_img = pil_img.convert('RGB')
                    
                    # 이미지 변조
                    scale_factor = random.uniform(0.8, 1.2)
                    new_size = (int(width * scale_factor), int(height * scale_factor))
                    pil_img = pil_img.resize(new_size, Image.LANCZOS)
                    
                    pil_img = ImageEnhance.Brightness(pil_img).enhance(random.uniform(0.85, 1.15))
                    pil_img = ImageEnhance.Contrast(pil_img).enhance(random.uniform(0.85, 1.15))
                    pil_img = ImageEnhance.Color(pil_img).enhance(random.uniform(0.9, 1.1))
                    
                    if random.choice([True, False]):
                        pil_img = pil_img.transpose(Image.FLIP_LEFT_RIGHT)
                    
                    new_filename = f"{keyword}_{random.randint(1000,9999)}_{valid_count+1}.jpg"
                    disguised_path = os.path.join(disguised_dir, new_filename)
                    
                    pil_img.save(disguised_path, 'JPEG', quality=random.randint(80, 95), optimize=True)
                    
                    disguised_images.append({
                        'original_url': img_url,
                        'disguised_path': disguised_path,  
                        'new_filename': new_filename,
                        'original_size': (width, height),
                        'new_size': new_size
                    })
                    
                    valid_count += 1
                    print(f"✅ 변조 완료: {new_filename}")
                    
                    if valid_count >= 5:
                        break
                        
            except Exception:
                continue
                
        except Exception:
            continue
    
    print(f"🎉 총 {valid_count}개 이미지 변조 완료!")
    return disguised_images, disguised_dir

def enhanced_blog_processor(url, keyword):
    print(f"📖 처리 중: {url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, timeout=15, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")

        text_elements = soup.find_all(['p', 'div', 'article', 'section'])
        text_content = " ".join([elem.get_text(strip=True) for elem in text_elements])
        
        if len(text_content) < 200:
            return {"error": "텍스트 너무 짧음", "url": url}
        
        try:
            language = detect(text_content) if len(text_content) > 50 else "en"
        except:
            language = "en"
        
        if language != "en":
            translated_text = translate_text(text_content[:800])
        else:
            translated_text = text_content[:800]
        
        disguised_images, disguised_dir = smart_image_downloader_with_disguise(soup, url, keyword)
        
        result = {
            "title": soup.title.string.strip() if soup.title and soup.title.string else "여행 경험기",
            "url": url,
            "language": language,
            "original_text": text_content[:800],
            "translated_text": translated_text,
            "text_length": len(text_content),
            "images": disguised_images,
            "images_count": len(disguised_images),
            "processed_at": datetime.utcnow().isoformat()
        }
        
        print(f"✅ 성공: {len(disguised_images)}개 이미지, {len(text_content)}자")
        return result
        
    except Exception as e:
        print(f"❌ 오류: {url} - {e}")
        return {"error": str(e), "url": url}

def multi_blog_processor(keyword="travel", location="Japan", max_blogs=5):
    print(f"💰 멀티 블로그 프로세싱 시작...")
    
    successful_results = []
    all_images = []
    
    for i, url in enumerate(TRAVEL_BLOG_URLS[:max_blogs]):
        print(f"\n📖 블로그 {i+1}/{max_blogs}: {url}")
        
        result = enhanced_blog_processor(url, keyword)
        
        if "error" not in result:
            successful_results.append(result)
            all_images.extend(result.get('images', []))
            print(f"💵 수집: 텍스트 {result['text_length']}자, 이미지 {result['images_count']}개")
        else:
            print(f"❌ 실패: {result.get('error')}")
    
    print(f"\n💸 멀티 프로세싱 완료!")
    return successful_results, all_images

def ultimate_content_mixer(blog_results, keyword="travel", location="Japan"):
    print(f"💰 Ultimate Content Mixer 시작...")
    
    if not blog_results:
        return {"error": "처리할 블로그 결과가 없습니다"}
    
    all_translated_texts = []
    for result in blog_results:
        if result.get('translated_text'):
            all_translated_texts.append(result['translated_text'])
    
    all_sentences = []
    for text in all_translated_texts:
        sentences = re.split(r'[.!?]+', text)
        valid_sentences = [s.strip() for s in sentences if len(s.strip()) > 15]
        all_sentences.extend(valid_sentences)
    
    random.shuffle(all_sentences)
    
    travel_sentences = [s for s in all_sentences if any(word in s.lower() for word in ['travel', 'trip', 'visit', 'journey'])]
    place_sentences = [s for s in all_sentences if any(word in s.lower() for word in ['place', 'city', 'area', 'location'])]
    experience_sentences = [s for s in all_sentences if any(word in s.lower() for word in ['experience', 'amazing', 'beautiful'])]
    
    money_article = {
        "title": f"The Ultimate Guide to {keyword.title()} in {location}: My Complete Experience",
        "introduction": f"When I first decided to explore {location} for the ultimate {keyword} experience, I had no idea just how incredible this journey would become. This comprehensive guide shares my authentic experience and insider tips.",
        "body_sections": [],
        "conclusion": f"My {keyword} journey in {location} has been absolutely transformative. I can't recommend it highly enough for anyone seeking an authentic {keyword} experience.",
        "seo_keywords": [keyword, location, f"{keyword} guide", f"{location} travel"],
        "word_count": 0
    }
    
    sections = [
        {
            "title": f"Why {location} is Perfect for {keyword.title()}",
            "sentences": travel_sentences[:6] + experience_sentences[:4],
            "intro": f"Let me tell you why {location} completely changed my perspective on {keyword}."
        },
        {
            "title": f"Best {keyword.title()} Spots in {location}",
            "sentences": place_sentences[:6] + experience_sentences[4:8],
            "intro": f"After exploring countless locations, these places truly stood out."
        },
        {
            "title": f"Essential {keyword.title()} Tips for {location}",
            "sentences": travel_sentences[6:10] + place_sentences[6:10],
            "intro": f"These practical tips will help you make the most of your {location} experience."
        }
    ]
    
    total_words = len(money_article["introduction"].split())
    
    for section in sections:
        if section["sentences"]:
            content = section["intro"] + " "
            sentence_content = " ".join(section["sentences"][:6])
            
            sentence_content = re.sub(r'\byou\b', 'I', sentence_content, flags=re.IGNORECASE)
            sentence_content = re.sub(r'\byour\b', 'my', sentence_content, flags=re.IGNORECASE)
            
            full_content = content + sentence_content
            
            money_article["body_sections"].append({
                "title": section["title"],
                "content": full_content
            })
            
            total_words += len(full_content.split())
    
    money_article["word_count"] = total_words
    return money_article

# Flask 라우트들
@app.route("/")
def home():
    return {
        "message": "💰 MoneyMaking_Crawler API v2.0 - Railway Edition",
        "status": "🚀 DEPLOYED ON RAILWAY",
        "purpose": "Automated Affiliate Content Generation",
        "endpoints": {
            "home": "/",
            "test": "/test",
            "money_crawl": "/money_crawl",
            "quick_money": "/quick_money"
        },
        "timestamp": datetime.utcnow().isoformat()
    }

@app.route("/test")
def test():
    return {
        "message": "💰 MoneyMaking_Crawler System Check",
        "google_cloud": "✅ Connected" if credentials else "❌ Not Connected",
        "google_drive": "✅ Connected" if drive_service else "❌ Not Connected",
        "target_blogs": len(TRAVEL_BLOG_URLS),
        "status": "🚀 READY TO EARN",
        "platform": "Railway",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.route("/money_crawl", methods=['GET', 'POST'])
def money_crawl():
    try:
        if request.method == 'GET':
            keyword = request.args.get("keyword", "travel")
            location = request.args.get("location", "Japan")
            max_blogs = int(request.args.get("max_blogs", "3"))
        else:
            data = request.get_json()
            keyword = data.get("keyword", "travel")
            location = data.get("location", "Japan")
            max_blogs = int(data.get("max_blogs", "3"))
        
        start_time = datetime.utcnow()
        
        # 1단계: 멀티 블로그 크롤링
        blog_results, all_images = multi_blog_processor(keyword, location, max_blogs)
        
        if not blog_results:
            return {
                "success": False,
                "error": "No blogs processed successfully",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # 2단계: 콘텐츠 믹싱
        money_article = ultimate_content_mixer(blog_results, keyword, location)
        
        if "error" in money_article:
            return {
                "success": False,
                "error": money_article["error"],
                "timestamp": datetime.utcnow().isoformat()
            }
        
        end_time = datetime.utcnow()
        processing_time = (end_time - start_time).total_seconds()
        estimated_earnings = round(money_article['word_count'] * 0.05, 2)
        
        return {
            "success": True,
            "money_making_info": {
                "estimated_earnings": f"${estimated_earnings}",
                "keyword": keyword,
                "location": location,
                "processing_time": f"{processing_time:.1f}s"
            },
            "content": {
                "title": money_article['title'],
                "word_count": money_article['word_count'],
                "sections_count": len(money_article['body_sections']),
                "seo_keywords": money_article['seo_keywords'],
                "full_article": money_article
            },
            "images": {
                "total_images": len(all_images),
                "tracking_prevented": True,
                "ready_for_use": True
            },
            "platform": "Railway",
            "timestamp": end_time.isoformat()
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@app.route("/quick_money")
def quick_money():
    try:
        blog_results, all_images = multi_blog_processor("travel", "Tokyo", 1)
        
        if blog_results:
            quick_article = ultimate_content_mixer(blog_results, "travel", "Tokyo")
            estimated_earnings = round(quick_article.get('word_count', 0) * 0.05, 2)
            
            return {
                "success": True,
                "estimated_earnings": f"${estimated_earnings}",
                "content_generated": True,
                "word_count": quick_article.get('word_count', 0),
                "images_collected": len(all_images),
                "platform": "Railway"
            }
        else:
            return {
                "success": False,
                "error": "Quick test failed"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
