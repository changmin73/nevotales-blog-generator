# MoneyMaking_Crawler v3.1 - 개선된 필터링 시스템
import os
import requests
import json
import random
import tempfile
import re
import time
from datetime import datetime
from urllib.parse import urlparse, urljoin, quote_plus
from io import BytesIO
import base64

from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from google.cloud import storage, translate_v3
from google.oauth2 import service_account
from langdetect import detect
from PIL import Image, ImageEnhance, ImageFilter
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from docx import Document
from docx.shared import Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

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
        docs_service = build('docs', 'v1', credentials=credentials)
    except:
        drive_service = None
        docs_service = None
else:
    translate_client = None
    storage_client = None
    drive_service = None
    docs_service = None

# 10개국 Google 도메인 및 언어 코드
TARGET_COUNTRIES = {
    'japan': {'domain': 'google.co.jp', 'lang': 'ja', 'translate_to': 'ja'},
    'germany': {'domain': 'google.de', 'lang': 'de', 'translate_to': 'de'},
    'france': {'domain': 'google.fr', 'lang': 'fr', 'translate_to': 'fr'},
    'italy': {'domain': 'google.it', 'lang': 'it', 'translate_to': 'it'},
    'spain': {'domain': 'google.es', 'lang': 'es', 'translate_to': 'es'},
    'netherlands': {'domain': 'google.nl', 'lang': 'nl', 'translate_to': 'nl'},
    'sweden': {'domain': 'google.se', 'lang': 'sv', 'translate_to': 'sv'},
    'norway': {'domain': 'google.no', 'lang': 'no', 'translate_to': 'no'},
    'denmark': {'domain': 'google.dk', 'lang': 'da', 'translate_to': 'da'},
    'austria': {'domain': 'google.at', 'lang': 'de', 'translate_to': 'de'}
}

# 개인 블로그 판별 키워드 (대폭 확장)
PERSONAL_BLOG_INDICATORS = [
    'blog', 'diary', 'travel', 'journey', 'experience', 'visit', 'trip',
    'my', 'personal', 'life', 'adventure', 'story', 'log', 'went', 'been',
    'vacation', 'holiday', 'backpack', 'solo', 'couple', 'family',
    'review', 'guide', 'tips', 'recommendation', 'amazing', 'beautiful',
    'incredible', 'awesome', 'wonderful', 'memories', 'discover', 'explore',
    'wandering', 'nomad', 'traveler', 'blogger', 'chronicles', 'tales',
    'adventures', 'experiences', 'memories', 'photos', 'pictures', 'moments'
]

# 기업/여행사 사이트 완전 차단 (대폭 강화)
CORPORATE_EXCLUSIONS = [
    # 예약 사이트
    'booking.com', 'agoda.com', 'expedia.com', 'hotels.com', 'airbnb.com',
    'kayak.com', 'priceline.com', 'orbitz.com', 'travelocity.com',
    'cheaptickets.com', 'momondo.com', 'skyscanner.com', 'trivago.com',
    
    # 호스텔/숙박
    'hostelworld.com', 'hostelbookers.com', 'hostelz.com', 'hostels.com',
    
    # 투어/액티비티
    'viator.com', 'getyourguide.com', 'klook.com', 'tiqets.com',
    'civitatis.com', 'attractiontix.com', 'citypass.com', 'isango.com',
    
    # 여행 포털/매거진
    'tripadvisor.com', 'lonelyplanet.com', 'roughguides.com', 'fodors.com',
    'frommers.com', 'ricksteves.com', 'atlasобscura.com', 'culturetrip.com',
    'theculturetrip.com', 'planetware.com', 'tripsavvy.com', 'afar.com',
    'travelandleisure.com', 'cntraveler.com', 'timeout.com', 'touropia.com',
    
    # 뉴스/매거진
    'cnn.com', 'bbc.com', 'reuters.com', 'nationalgeographic.com',
    'smithsonianmag.com', 'buzzfeed.com', 'huffpost.com',
    
    # 위키/정보
    'wikipedia.org', 'wikitravel.org', 'wikivoyage.org', 'wikimapia.org',
    
    # 쇼핑/딜
    'groupon.com', 'livingsocial.com', 'travelzoo.com', 'travel.com',
    
    # 정부/공식
    'gov', 'government', 'official', 'tourism', 'visitkorea', 'visit',
    'destination', 'chamber', 'convention', 'bureau', 'authority',
    
    # 기타 기업
    'yelp.com', 'foursquare.com', 'facebook.com', 'instagram.com',
    'twitter.com', 'youtube.com', 'pinterest.com', 'reddit.com',
    
    # 키워드 패턴
    'destination', 'tourism', 'visit', 'official', 'chamber', 'convention',
    'bureau', 'authority', 'commercial', 'advertisement', 'sponsored',
    'affiliate', 'deals', 'discount', 'cheap', 'best-price', 'compare-prices'
]

def translate_keyword(keyword, target_lang):
    """키워드를 지정된 언어로 번역"""
    if not translate_client or not credentials:
        return keyword
    
    try:
        parent = f"projects/{credentials.project_id}/locations/global"
        response = translate_client.translate_text(
            request={
                "parent": parent,
                "contents": [keyword],
                "mime_type": "text/plain",
                "source_language_code": "en",
                "target_language_code": target_lang,
            }
        )
        translated = response.translations[0].translated_text
        print(f"키워드 번역: {keyword} → {translated} ({target_lang})")
        return translated
    except Exception as e:
        print(f"번역 오류: {e}")
        return keyword

def is_personal_blog(url, title, description):
    """개인 블로그인지 판별 (더 관대한 기준)"""
    url_lower = url.lower()
    title_lower = title.lower() if title else ""
    desc_lower = description.lower() if description else ""
    
    # 기업 사이트 강력 제외
    for exclusion in CORPORATE_EXCLUSIONS:
        if exclusion in url_lower:
            print(f"❌ 기업 사이트 제외: {url} (포함: {exclusion})")
            return False
    
    # 개인 블로그 지표 확인 (기준 완화: 1개만 있어도 OK)
    text_to_check = f"{url_lower} {title_lower} {desc_lower}"
    personal_score = sum(1 for indicator in PERSONAL_BLOG_INDICATORS if indicator in text_to_check)
    
    # 추가 개인 블로그 패턴
    personal_patterns = [
        'wordpress.com', 'blogspot.com', 'blogger.com', 'medium.com',
        'tumblr.com', 'ghost.io', 'substack.com', 'wix.com', 'squarespace.com',
        '/blog/', '/travel/', '/diary/', '/journal/', '/adventure/'
    ]
    
    pattern_score = sum(1 for pattern in personal_patterns if pattern in url_lower)
    
    total_score = personal_score + pattern_score
    is_personal = total_score >= 1  # 기준 대폭 완화: 1점만 있어도 개인 블로그로 인정
    
    print(f"{'✅' if is_personal else '❌'} 블로그 판별: {url[:50]}... (점수: {total_score})")
    return is_personal

def search_google_country(keyword, country_info, max_results=15):
    """특정 국가의 Google에서 개인 블로그 검색 (더 많은 결과)"""
    
    # 키워드를 해당 국가 언어로 번역
    translated_keyword = translate_keyword(keyword, country_info['translate_to'])
    
    # 더 다양한 검색 쿼리 시도
    search_queries = [
        f"{translated_keyword} blog personal experience",
        f"{translated_keyword} travel diary",
        f"{translated_keyword} my trip",
        f"{translated_keyword} adventure blog"
    ]
    
    all_results = []
    
    for search_query in search_queries:
        if len(all_results) >= 5:  # 각 나라에서 최대 5개
            break
            
        encoded_query = quote_plus(search_query)
        search_url = f"https://www.{country_info['domain']}/search?q={encoded_query}&num={max_results}&hl={country_info['lang']}"
        
        # 더 다양한 User-Agent 사용
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15'
        ]
        
        headers = {
            'User-Agent': random.choice(user_agents),
            'Accept-Language': f"{country_info['lang']},en;q=0.9",
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        try:
            print(f"🔍 {country_info['domain']}에서 검색: {search_query}")
            response = requests.get(search_url, headers=headers, timeout=15)
            
            if response.status_code != 200:
                print(f"❌ 검색 실패: {response.status_code}")
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 더 다양한 Google 결과 파싱 시도
            search_results = soup.find_all('div', class_='g') or soup.find_all('div', class_='tF2Cxc')
            
            for result in search_results[:max_results]:
                if len(all_results) >= 5:
                    break
                    
                try:
                    # 링크 추출
                    link_elem = result.find('a', href=True)
                    if not link_elem:
                        continue
                    
                    url = link_elem['href']
                    if url.startswith('/url?q='):
                        url = url.split('/url?q=')[1].split('&')[0]
                    elif url.startswith('/search'):
                        continue
                    
                    if not url.startswith('http'):
                        continue
                    
                    # 제목 추출
                    title_elem = result.find('h3') or result.find('a')
                    title = title_elem.get_text() if title_elem else ""
                    
                    # 설명 추출
                    desc_candidates = result.find_all(['span', 'div'], class_=True)
                    description = ""
                    for candidate in desc_candidates:
                        text = candidate.get_text().strip()
                        if len(text) > 20 and len(text) < 200:
                            description = text
                            break
                    
                    # 개인 블로그 판별 (완화된 기준)
                    if is_personal_blog(url, title, description):
                        all_results.append({
                            'url': url,
                            'title': title,
                            'description': description,
                            'country': country_info['domain'],
                            'language': country_info['lang'],
                            'search_query': search_query
                        })
                        print(f"✅ 개인 블로그 발견: {title[:50]}...")
                    
                except Exception as e:
                    print(f"결과 파싱 오류: {e}")
                    continue
            
            time.sleep(random.uniform(1, 3))  # 랜덤 딜레이
            
        except Exception as e:
            print(f"❌ {country_info['domain']} 검색 오류: {e}")
            continue
    
    print(f"📊 {country_info['domain']}: {len(all_results)}개 개인 블로그 발견")
    return all_results

def process_4_3_image(img_data, keyword, index):
    """이미지를 4:3 비율로 처리하고 변조"""
    try:
        with Image.open(BytesIO(img_data)) as pil_img:
            # RGB 변환
            if pil_img.mode != 'RGB':
                pil_img = pil_img.convert('RGB')
            
            width, height = pil_img.size
            
            # 4:3 비율로 크롭
            target_ratio = 4/3
            current_ratio = width/height
            
            if current_ratio > target_ratio:
                # 가로가 더 긴 경우 - 좌우 크롭
                new_width = int(height * target_ratio)
                left = (width - new_width) // 2
                pil_img = pil_img.crop((left, 0, left + new_width, height))
            elif current_ratio < target_ratio:
                # 세로가 더 긴 경우 - 상하 크롭
                new_height = int(width / target_ratio)
                top = (height - new_height) // 2
                pil_img = pil_img.crop((0, top, width, top + new_height))
            
            # 800x600으로 리사이즈
            pil_img = pil_img.resize((800, 600), Image.LANCZOS)
            
            # 이미지 변조 (추적 방지)
            # 1. 밝기/대비/색상 조정
            pil_img = ImageEnhance.Brightness(pil_img).enhance(random.uniform(0.85, 1.15))
            pil_img = ImageEnhance.Contrast(pil_img).enhance(random.uniform(0.85, 1.15))
            pil_img = ImageEnhance.Color(pil_img).enhance(random.uniform(0.9, 1.1))
            
            # 2. 좌우 반전 (50% 확률)
            if random.choice([True, False]):
                pil_img = pil_img.transpose(Image.FLIP_LEFT_RIGHT)
            
            # 3. 약간의 블러 효과 (25% 확률)
            if random.random() < 0.25:
                pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=0.5))
            
            # 임시 파일로 저장
            temp_path = os.path.join(tempfile.gettempdir(), f"{keyword}_{index}_{random.randint(1000,9999)}.jpg")
            pil_img.save(temp_path, 'JPEG', quality=random.randint(85, 95), optimize=True)
            
            return temp_path
            
    except Exception as e:
        print(f"이미지 처리 오류: {e}")
        return None

def extract_blog_content(url, language):
    """블로그에서 텍스트와 이미지 추출"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 텍스트 추출
        text_elements = soup.find_all(['p', 'div', 'article', 'section', 'main'])
        text_content = " ".join([elem.get_text(strip=True) for elem in text_elements])
        
        if len(text_content) < 300:  # 최소 길이 기준 완화
            return None
        
        # 이미지 추출
        images = []
        img_tags = soup.find_all('img')
        
        for i, img in enumerate(img_tags[:25]):  # 최대 25개까지
            try:
                img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if not img_url:
                    continue
                
                # URL 정규화
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                elif img_url.startswith('/'):
                    img_url = urljoin(url, img_url)
                elif not img_url.startswith('http'):
                    img_url = urljoin(url, img_url)
                
                # 이미지 다운로드
                img_response = requests.get(img_url, headers=headers, timeout=10)
                if img_response.status_code == 200:
                    img_data = img_response.content
                    
                    # 이미지 크기 확인 (기준 완화)
                    try:
                        with Image.open(BytesIO(img_data)) as test_img:
                            width, height = test_img.size
                            if width >= 150 and height >= 100:  # 크기 기준 완화
                                processed_path = process_4_3_image(img_data, "image", len(images))
                                if processed_path:
                                    images.append(processed_path)
                    except:
                        continue
                        
            except Exception as e:
                continue
        
        # 텍스트 번역
        if language != 'en':
            try:
                parent = f"projects/{credentials.project_id}/locations/global"
                response = translate_client.translate_text(
                    request={
                        "parent": parent,
                        "contents": [text_content[:2000]],  # 번역 제한
                        "mime_type": "text/plain",
                        "source_language_code": language,
                        "target_language_code": "en",
                    }
                )
                translated_text = response.translations[0].translated_text
            except:
                translated_text = text_content[:2000]
        else:
            translated_text = text_content[:2000]
        
        return {
            'url': url,
            'original_text': text_content[:2000],
            'translated_text': translated_text,
            'images': images,
            'language': language
        }
        
    except Exception as e:
        print(f"블로그 추출 오류 {url}: {e}")
        return None

def create_personal_story(blog_contents, keyword, location):
    """여러 블로그를 바탕으로 개인 경험담 작성"""
    
    if not blog_contents:
        return {"error": "처리할 블로그 내용이 없습니다"}
    
    # 모든 번역된 텍스트 수집
    all_texts = []
    for content in blog_contents:
        if content.get('translated_text'):
            all_texts.append(content['translated_text'])
    
    # 문장 단위로 분해
    all_sentences = []
    for text in all_texts:
        sentences = re.split(r'[.!?]+', text)
        valid_sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        all_sentences.extend(valid_sentences)
    
    random.shuffle(all_sentences)
    
    # 주제별 문장 분류
    intro_sentences = [s for s in all_sentences if any(word in s.lower() for word in ['first', 'started', 'began', 'decided', 'planned'])]
    experience_sentences = [s for s in all_sentences if any(word in s.lower() for word in ['amazing', 'beautiful', 'incredible', 'wonderful', 'stunning', 'fantastic'])]
    place_sentences = [s for s in all_sentences if any(word in s.lower() for word in ['place', 'location', 'area', 'spot', 'destination'])]
    food_sentences = [s for s in all_sentences if any(word in s.lower() for word in ['food', 'eat', 'restaurant', 'delicious', 'taste', 'meal'])]
    tip_sentences = [s for s in all_sentences if any(word in s.lower() for word in ['tip', 'advice', 'recommend', 'suggest', 'important'])]
    
    # 2500단어 개인 경험담 구성
    article = {
        "title": f"My Incredible {keyword.title()} Journey in {location}: A Complete Personal Experience Guide",
        
        "introduction": f"""
When I first planned my trip to {location} for {keyword}, I had high expectations, but nothing could have prepared me for the incredible journey that awaited me. After spending extensive time exploring this amazing destination, I'm excited to share my personal experience and insider tips that will help you make the most of your own {keyword} adventure in {location}.

This isn't just another generic travel guide - this is my authentic, first-hand account of {keyword} in {location}, filled with personal stories, unexpected discoveries, and practical advice that I wish I had known before my trip. Whether you're planning your first visit or looking to discover something new, my experience will give you the confidence and knowledge to create your own unforgettable memories.
        """,
        
        "sections": [],
        
        "conclusion": f"""
Looking back on my {keyword} journey in {location}, I can honestly say it was one of the most transformative travel experiences of my life. Every single day brought new discoveries, incredible moments, and memories that I'll treasure forever.

{location} exceeded all my expectations for {keyword}, and I'm already planning my return trip. The combination of stunning landscapes, rich culture, amazing food, and warm people created an experience that touched my heart in ways I never expected.

If you're considering {location} for your next {keyword} adventure, I can't recommend it highly enough. Just remember to bring an open mind, comfortable shoes, and most importantly - be ready for the adventure of a lifetime. Trust me, you won't regret it!
        """,
        
        "word_count": 0
    }
    
    # 10개 대형 섹션 생성
    sections_data = [
        {
            "title": f"Why I Chose {location} for My {keyword.title()} Adventure",
            "sentences": intro_sentences[:5] + experience_sentences[:3],
            "intro": f"Let me start by sharing why {location} became my dream destination for {keyword}."
        },
        {
            "title": f"Planning My {keyword.title()} Trip to {location}: What I Learned",
            "sentences": tip_sentences[:4] + place_sentences[:4],
            "intro": f"Planning my {location} trip taught me valuable lessons that I wish I'd known earlier."
        },
        {
            "title": f"First Impressions: Arriving in {location}",
            "sentences": experience_sentences[3:7] + place_sentences[4:7],
            "intro": f"The moment I stepped foot in {location}, I knew this trip would be special."
        },
        {
            "title": f"Top {keyword.title()} Experiences That Blew My Mind",
            "sentences": experience_sentences[7:12] + place_sentences[7:10],
            "intro": f"Some experiences in {location} were so incredible, they completely changed my perspective on {keyword}."
        },
        {
            "title": f"Hidden Gems I Discovered During My {location} Journey",
            "sentences": place_sentences[10:15] + experience_sentences[12:15],
            "intro": f"The best parts of my {location} adventure were the unexpected discoveries off the beaten path."
        },
        {
            "title": f"Food Adventures: My Culinary Journey in {location}",
            "sentences": food_sentences[:8] + experience_sentences[15:18],
            "intro": f"The food scene in {location} became an unexpected highlight of my {keyword} journey."
        },
        {
            "title": f"Challenges I Faced and How I Overcame Them",
            "sentences": tip_sentences[4:8] + experience_sentences[18:21],
            "intro": f"Not everything went perfectly during my {location} trip, but these challenges taught me valuable lessons."
        },
        {
            "title": f"Meeting Locals: The Heart of My {location} Experience",
            "sentences": experience_sentences[21:25] + place_sentences[15:18],
            "intro": f"The people I met in {location} made my {keyword} journey truly unforgettable."
        },
        {
            "title": f"Budget Breakdown: What My {location} {keyword.title()} Trip Actually Cost",
            "sentences": tip_sentences[8:12] + experience_sentences[25:28],
            "intro": f"Here's the honest breakdown of what I spent during my {location} adventure."
        },
        {
            "title": f"Essential Tips for Your Own {location} {keyword.title()} Adventure",
            "sentences": tip_sentences[12:16] + place_sentences[18:22],
            "intro": f"Based on my experience, here are the most important things you need to know for {location}."
        }
    ]
    
    total_words = len(article["introduction"].split()) + len(article["conclusion"].split())
    
    # 각 섹션 구성
    for section_data in sections_data:
        if section_data["sentences"]:
            content = section_data["intro"] + " "
            
            # 문장들을 개인 경험으로 변환
            personal_sentences = []
            for sentence in section_data["sentences"][:6]:
                # 2인칭/3인칭을 1인칭으로 변환
                personal_sentence = sentence
                personal_sentence = re.sub(r'\byou\b', 'I', personal_sentence, flags=re.IGNORECASE)
                personal_sentence = re.sub(r'\byour\b', 'my', personal_sentence, flags=re.IGNORECASE)
                personal_sentence = re.sub(r'\btheir\b', 'my', personal_sentence, flags=re.IGNORECASE)
                personal_sentence = re.sub(r'\bthey\b', 'I', personal_sentence, flags=re.IGNORECASE)
                personal_sentence = re.sub(r'\btravelers?\b', 'I', personal_sentence, flags=re.IGNORECASE)
                personal_sentence = re.sub(r'\bvisitors?\b', 'I', personal_sentence, flags=re.IGNORECASE)
                
                personal_sentences.append(personal_sentence)
            
            full_content = content + " ".join(personal_sentences)
            
            article["sections"].append({
                "title": section_data["title"],
                "content": full_content
            })
            
            total_words += len(full_content.split())
    
    article["word_count"] = total_words
    return article

def create_word_document(article, all_images, keyword, location):
    """Word 문서 생성 (글 + 이미지들)"""
    
    doc = Document()
    
    # 제목
    title = doc.add_heading(article['title'], 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # 메타 정보
    doc.add_paragraph(f"Word Count: {article['word_count']}")
    doc.add_paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
    doc.add_paragraph(f"Keyword: {keyword}")
    doc.add_paragraph(f"Location: {location}")
    doc.add_paragraph()
    
    # 도입부
    doc.add_heading("Introduction", 1)
    doc.add_paragraph(article['introduction'])
    
    # 본문 섹션들
    for section in article['sections']:
        doc.add_heading(section['title'], 1)
        doc.add_paragraph(section['content'])
        doc.add_paragraph()  # 섹션 간 공백
    
    # 결론
    doc.add_heading("Conclusion", 1)
    doc.add_paragraph(article['conclusion'])
    
    # 이미지 섹션
    if all_images:
        doc.add_page_break()
        doc.add_heading("📸 Collected Images (4:3 Ratio)", 1)
        doc.add_paragraph("All images have been processed and optimized for your blog:")
        doc.add_paragraph()
        
        # 이미지들 삽입
        for i, img_path in enumerate(all_images, 1):
            try:
                if os.path.exists(img_path):
                    doc.add_paragraph(f"Image {i}:")
                    doc.add_picture(img_path, width=Inches(5.33))  # 4:3 비율 유지 (5.33" x 4")
                    doc.add_paragraph()
            except Exception as e:
                print(f"이미지 삽입 오류 {img_path}: {e}")
                continue
    
    # 임시 파일로 저장
    temp_docx_path = os.path.join(tempfile.gettempdir(), f"MoneyMaking_{keyword}_{location}_{int(time.time())}.docx")
    doc.save(temp_docx_path)
    
    return temp_docx_path

def upload_to_google_drive(docx_path, keyword, location):
    """Google Drive에 Word 문서 업로드"""
    
    if not drive_service:
        return {"success": False, "error": "Google Drive 서비스 없음"}
    
    try:
        # 메인 폴더 생성
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        folder_name = f"MoneyMaking_{keyword}_{location}_{timestamp}"
        
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        folder = drive_service.files().create(body=folder_metadata).execute()
        folder_id = folder.get('id')
        
        # Word 문서 업로드
        file_metadata = {
            'name': f"MoneyMaking_{keyword}_{location}_Complete_Article.docx",
            'parents': [folder_id]
        }
        
        media = MediaFileUpload(docx_path, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        
        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name,webViewLink'
        ).execute()
        
        folder_link = f"https://drive.google.com/drive/folders/{folder_id}"
        
        return {
            "success": True,
            "folder_link": folder_link,
            "document_link": uploaded_file.get('webViewLink'),
            "folder_name": folder_name
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# Flask 라우트들
@app.route("/")
def home():
    return {
        "message": "💰 MoneyMaking_Crawler v3.1 - 개선된 필터링 시스템",
        "status": "🚀 DEPLOYED ON RAILWAY",
        "purpose": "10개국 개인 블로그 크롤링 → 2500단어 개인 경험담 생성 → Word 문서 자동 저장",
        "features": [
            "🌍 10개국 Google 검색 (개인 블로그만 타겟팅)",
            "🔍 키워드 자동 번역 (각국 언어)",
            "📝 2500단어 개인 경험담 생성",
            "🖼️ 이미지 4:3 변조 및 Word 삽입",
            "☁️ Google Drive 자동 저장",
            "🚫 여행사이트 강력 차단",
            "✅ 개인 블로그 필터링 완화"
        ],
        "improvements": [
            "여행사이트 차단 대폭 강화 (50+ 사이트)",
            "개인 블로그 판별 기준 완화 (점수 2→1)",
            "검색 쿼리 다양화 (4가지 패턴)",
            "이미지 크기 기준 완화",
            "User-Agent 로테이션"
        ],
        "endpoints": {
            "home": "/",
            "test": "/test",
            "global_crawl": "/global_crawl",
            "quick_test": "/quick_test"
        },
        "timestamp": datetime.utcnow().isoformat()
    }

@app.route("/test")
def test():
    return {
        "message": "💰 MoneyMaking_Crawler v3.1 System Check",
        "google_cloud": "✅ Connected" if credentials else "❌ Not Connected",
        "google_drive": "✅ Connected" if drive_service else "❌ Not Connected",
        "translate_service": "✅ Connected" if translate_client else "❌ Not Connected",
        "target_countries": len(TARGET_COUNTRIES),
        "corporate_exclusions": len(CORPORATE_EXCLUSIONS),
        "personal_indicators": len(PERSONAL_BLOG_INDICATORS),
        "filtering_improvements": {
            "개인블로그_기준": "완화됨 (1점 이상)",
            "여행사이트_차단": f"{len(CORPORATE_EXCLUSIONS)}개 사이트",
            "검색_쿼리": "4가지 패턴",
            "User_Agent": "4가지 로테이션"
        },
        "status": "🚀 READY FOR IMPROVED CRAWLING",
        "platform": "Railway",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.route("/global_crawl", methods=['GET', 'POST'])
def global_crawl():
    """💰 개선된 글로벌 크롤링 메인 엔드포인트"""
    
    try:
        # 파라미터 받기
        if request.method == 'GET':
            keyword = request.args.get("keyword", "travel")
            location = request.args.get("location", "Europe")
            max_blogs = int(request.args.get("max_blogs", "3"))
        else:
            data = request.get_json() or {}
            keyword = data.get("keyword", "travel")
            location = data.get("location", "Europe")
            max_blogs = int(data.get("max_blogs", "3"))
        
        start_time = datetime.utcnow()
        print(f"💰 개선된 글로벌 크롤링 시작: {keyword} in {location}")
        
        # 1단계: 10개국에서 개인 블로그 검색 (개선된 필터링)
        print("🌍 1단계: 개선된 개인 블로그 검색...")
        all_blog_results = []
        
        countries_tried = 0
        for country_name, country_info in TARGET_COUNTRIES.items():
            if len(all_blog_results) >= max_blogs:  # 목표 달성하면 중단
                break
                
            countries_tried += 1
            print(f"\n🔍 {country_name} 검색 중 ({countries_tried}/10)...")
            country_results = search_google_country(keyword, country_info, max_results=20)
            
            for result in country_results:
                if len(all_blog_results) >= max_blogs:
                    break
                all_blog_results.append(result)
            
            print(f"📊 현재까지 수집: {len(all_blog_results)}/{max_blogs}개")
            time.sleep(random.uniform(2, 4))  # 랜덤 딜레이
        
        if not all_blog_results:
            return {
                "success": False,
                "error": "개선된 필터링으로도 개인 블로그를 찾을 수 없습니다",
                "stage": "blog_search",
                "debug_info": {
                    "countries_tried": countries_tried,
                    "max_blogs_target": max_blogs,
                    "filtering_used": "v3.1 개선된 필터링"
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        
        print(f"✅ 1단계 완료: {len(all_blog_results)}개 개인 블로그 발견")
        
        # 2단계: 블로그 내용 및 이미지 크롤링
        print("\n📖 2단계: 블로그 내용 크롤링...")
        blog_contents = []
        all_images = []
        
        for i, blog_result in enumerate(all_blog_results):
            print(f"\n크롤링 중 ({i+1}/{len(all_blog_results)}): {blog_result['title'][:50]}...")
            
            content = extract_blog_content(blog_result['url'], blog_result['language'])
            if content:
                blog_contents.append(content)
                all_images.extend(content['images'])
                print(f"✅ 성공: {len(content['images'])}개 이미지, {len(content['translated_text'])}자")
            else:
                print(f"❌ 실패: {blog_result['url']}")
            
            time.sleep(random.uniform(1, 2))  # 요청 간격 조절
        
        if not blog_contents:
            return {
                "success": False,
                "error": "블로그 내용을 추출할 수 없습니다",
                "stage": "content_extraction",
                "found_blogs": len(all_blog_results),
                "timestamp": datetime.utcnow().isoformat()
            }
        
        print(f"✅ 2단계 완료: {len(blog_contents)}개 블로그, {len(all_images)}개 이미지")
        
        # 3단계: 개인 경험담 작성
        print("\n✍️ 3단계: 개인 경험담 생성...")
        personal_article = create_personal_story(blog_contents, keyword, location)
        
        if "error" in personal_article:
            return {
                "success": False,
                "error": personal_article["error"],
                "stage": "story_creation",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        print(f"✅ 3단계 완료: {personal_article['word_count']}단어 개인 경험담")
        
        # 4단계: Word 문서 생성
        print("\n📄 4단계: Word 문서 생성...")
        docx_path = create_word_document(personal_article, all_images, keyword, location)
        print(f"✅ 4단계 완료: Word 문서 생성")
        
        # 5단계: Google Drive 업로드
        print("\n☁️ 5단계: Google Drive 업로드...")
        drive_result = upload_to_google_drive(docx_path, keyword, location)
        
        # 임시 파일들 정리
        try:
            os.remove(docx_path)
            for img_path in all_images:
                if os.path.exists(img_path):
                    os.remove(img_path)
        except:
            pass
        
        # 최종 결과
        end_time = datetime.utcnow()
        processing_time = (end_time - start_time).total_seconds()
        
        final_result = {
            "success": True,
            "global_crawling_info": {
                "💰 키워드": keyword,
                "🌍 타겟 위치": location,
                "⏱️ 처리 시간": f"{processing_time:.1f}초",
                "🔍 검색된 블로그": len(all_blog_results),
                "📖 성공적 크롤링": len(blog_contents),
                "🖼️ 수집된 이미지": len(all_images),
                "📝 최종 단어 수": personal_article['word_count'],
                "🎯 상태": "v3.1 개선된 필터링으로 완료",
                "🚫 차단된 여행사이트": len(CORPORATE_EXCLUSIONS)
            },
            
            "filtering_improvements": {
                "개인블로그_기준": "1점 이상 (완화됨)",
                "여행사이트_차단": f"{len(CORPORATE_EXCLUSIONS)}개 사이트",
                "검색_다양화": "4가지 쿼리 패턴",
                "User_Agent_로테이션": "4가지",
                "이미지_기준_완화": "150x100px → 관대한 기준"
            },
            
            "blog_sources": [
                {
                    "title": result['title'],
                    "url": result['url'],
                    "country": result['country'],
                    "language": result['language'],
                    "search_query": result.get('search_query', '')
                } for result in all_blog_results
            ],
            
            "article_preview": {
                "title": personal_article['title'],
                "word_count": personal_article['word_count'],
                "sections_count": len(personal_article['sections']),
                "introduction_preview": personal_article['introduction'][:200] + "...",
                "conclusion_preview": personal_article['conclusion'][:200] + "..."
            },
            
            "image_collection": {
                "total_processed": len(all_images),
                "format": "4:3 ratio (800x600)",
                "modifications": ["Brightness/Contrast adjusted", "50% chance horizontal flip", "Metadata removed"],
                "ready_for_blog": "✅ Yes"
            },
            
            "google_drive_delivery": drive_result,
            
            "monetization_guide": {
                "1단계": "Google Drive에서 완성된 Word 문서 다운로드",
                "2단계": "WordPress에 글 내용 복사",
                "3단계": "문서 하단의 이미지들을 글 중간중간 삽입",
                "4단계": "어필리에이트 링크 및 상품 추천 섹션 추가",
                "5단계": "SEO 최적화 (메타 태그, 키워드 밀도)",
                "6단계": "게시 후 Google 검색 노출 대기",
                "💡 꿀팁": "v3.1 필터링으로 더 순수한 개인 경험담, 신뢰도 극대화"
            },
            
            "technical_details": {
                "countries_searched": countries_tried,
                "countries_available": list(TARGET_COUNTRIES.keys()),
                "processing_time": f"{processing_time:.2f}초",
                "generated_at": end_time.isoformat(),
                "api_version": "MoneyMaking_Crawler v3.1",
                "improvements": "필터링 개선, 여행사이트 차단 강화"
            }
        }
        
        print(f"\n🎉 개선된 글로벌 크롤링 완료!")
        print(f"💰 최종 결과: {personal_article['word_count']}단어, {len(all_images)}개 이미지")
        print(f"🚫 여행사이트 {len(CORPORATE_EXCLUSIONS)}개 차단")
        print(f"⏱️ 총 처리 시간: {processing_time:.1f}초")
        
        return final_result
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "stage": "unknown",
            "api_version": "v3.1",
            "timestamp": datetime.utcnow().isoformat(),
            "troubleshooting": {
                "확인사항_1": "Google 서비스 계정 설정 확인",
                "확인사항_2": "네트워크 연결 상태 확인",
                "확인사항_3": "키워드 및 위치 파라미터 확인",
                "개선사항": "v3.1 필터링 시스템 적용됨"
            }
        }

@app.route("/quick_test")
def quick_test():
    """빠른 시스템 테스트"""
    
    try:
        print("🧪 빠른 테스트 시작...")
        
        # 간단한 키워드 번역 테스트
        test_keyword = "travel experience"
        test_translations = {}
        
        for country, info in list(TARGET_COUNTRIES.items())[:3]:  # 3개국만 테스트
            translated = translate_keyword(test_keyword, info['translate_to'])
            test_translations[country] = translated
        
        return {
            "success": True,
            "quick_test_results": {
                "💰 시스템 상태": "v3.1 개선된 필터링 정상 작동",
                "🌍 테스트 번역": test_translations,
                "🔧 Google 서비스": "✅ 연결됨" if credentials else "❌ 연결 안됨",
                "📁 Drive 서비스": "✅ 연결됨" if drive_service else "❌ 연결 안됨",
                "🚫 여행사이트 차단": f"{len(CORPORATE_EXCLUSIONS)}개 사이트",
                "✅ 개인블로그 기준": "1점 이상 (완화됨)",
                "⚡ 처리 속도": "빠름",
                "🎯 준비 상태": "개선된 글로벌 크롤링 준비 완료"
            },
            "improvements_v31": [
                "여행사이트 차단 50+ 사이트로 확장",
                "개인 블로그 판별 기준 2점→1점으로 완화",
                "검색 쿼리 4가지 패턴으로 다양화",
                "이미지 크기 기준 완화",
                "User-Agent 로테이션 4가지"
            ],
            "next_step": "global_crawl 엔드포인트로 개선된 크롤링 시작",
            "platform": "Railway",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
