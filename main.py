from flask import Flask, request, jsonify
import os
import requests
from bs4 import BeautifulSoup
import openai
from PIL import Image, ImageEnhance
import random
from io import BytesIO
import base64
from pyairtable import Api
import json
from datetime import datetime
import hashlib

app = Flask(__name__)

# 환경변수 설정
openai.api_key = os.getenv('OPENAI_API_KEY')
AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
MAKE_WEBHOOK_URL = os.getenv('MAKE_WEBHOOK_URL')

# Airtable 초기화
airtable = Api(AIRTABLE_API_KEY)
table = airtable.table(AIRTABLE_BASE_ID, 'Blog_Images')  # 테이블 이름 확인 필요

class BlogProcessor:
    def __init__(self):
        self.processed_images = []
        
    def extract_content_from_html(self, html_list):
        """HTML 리스트에서 텍스트와 이미지 추출"""
        all_texts = []
        all_images = []
        
        for html in html_list:
            soup = BeautifulSoup(html, 'html.parser')
            
            # 텍스트 추출
            text = soup.get_text(strip=True)
            all_texts.append(text)
            
            # 이미지 추출
            for img in soup.find_all('img'):
                src = img.get('src')
                if src and self.is_valid_image(src):
                    all_images.append({
                        'url': src,
                        'alt': img.get('alt', '')
                    })
        
        return all_texts, all_images
    
    def is_valid_image(self, url):
        """이미지가 사용 가능한지 확인"""
        # 아이콘, 로고, 배너 제외
        skip_keywords = ['icon', 'logo', 'banner', 'button', 'avatar']
        return not any(keyword in url.lower() for keyword in skip_keywords)
    
    def translate_to_english(self, texts):
        """GPT를 사용해 영어로 번역"""
        combined_text = "\n\n".join(texts[:5])  # 최대 5개만
        
        prompt = f"""
        Translate the following travel blog excerpts to English. 
        Keep the personal, experiential tone:
        
        {combined_text[:3000]}  # 토큰 제한
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a professional translator."},
                {"role": "user", "content": prompt}
            ]
        )
        
        return response.choices[0].message.content
    
    def create_blog_post(self, translated_texts, keyword):
        """2500단어 블로그 포스트 생성"""
        prompt = f"""
        Based on these travel experiences about {keyword}, create a comprehensive 
        2500-word travel blog post in first person. Include:
        
        1. Engaging introduction about visiting {keyword}
        2. Detailed experiences and tips
        3. Personal anecdotes and emotions
        4. Practical information for travelers
        5. Compelling conclusion
        
        Source material:
        {translated_texts[:4000]}
        
        Write as if you personally visited all these places. Make it natural, 
        engaging, and helpful for American travelers.
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo-16k",  # 긴 응답을 위해
            messages=[
                {"role": "system", "content": "You are an experienced travel blogger writing for American audience."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=3000
        )
        
        return response.choices[0].message.content
    
    def process_image(self, image_url):
        """이미지 다운로드 및 변형"""
        try:
            # 이미지 다운로드
            response = requests.get(image_url)
            img = Image.open(BytesIO(response.content))
            
            # RGB 변환
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 변형 적용
            # 크기 조정 (95-105%)
            scale = random.uniform(0.95, 1.05)
            new_size = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # 밝기, 대비, 색상 조정
            brightness = ImageEnhance.Brightness(img)
            img = brightness.enhance(random.uniform(0.95, 1.05))
            
            contrast = ImageEnhance.Contrast(img)
            img = contrast.enhance(random.uniform(0.95, 1.05))
            
            # 이미지를 바이트로 변환
            buffered = BytesIO()
            img.save(buffered, format="JPEG", quality=random.randint(85, 95))
            img_bytes = buffered.getvalue()
            
            return img_bytes, img.size
            
        except Exception as e:
            print(f"Error processing image {image_url}: {str(e)}")
            return None, None
    
    def upload_to_airtable(self, image_bytes, filename, alt_text, keyword):
        """Airtable에 이미지 업로드"""
        try:
            # Base64 인코딩
            img_base64 = base64.b64encode(image_bytes).decode()
            
            # Airtable 레코드 생성
            record = table.create({
                'Image': [{'url': f'data:image/jpeg;base64,{img_base64}'}],
                'Alt_Text': alt_text,
                'Blog_Title': f"{keyword} Travel Guide",
                'Created_Date': datetime.now().isoformat()
            })
            
            # 업로드된 이미지 URL 반환
            return record['fields']['Image'][0]['url']
            
        except Exception as e:
            print(f"Error uploading to Airtable: {str(e)}")
            return None

@app.route('/process-blog', methods=['POST'])
def process_blog():
    """Make.com에서 호출할 메인 엔드포인트"""
    try:
        data = request.json
        html_contents = data.get('html_contents', [])  # 5개 HTML
        keyword = data.get('keyword', 'travel')
        
        processor = BlogProcessor()
        
        # 1. HTML에서 컨텐츠 추출
        texts, images = processor.extract_content_from_html(html_contents)
        
        # 2. 영어로 번역
        translated = processor.translate_to_english(texts)
        
        # 3. 블로그 포스트 생성
        blog_post = processor.create_blog_post(translated, keyword)
        
        # 4. 이미지 처리 및 Airtable 업로드
        processed_images = []
        for idx, img_data in enumerate(images[:10]):  # 최대 10개
            img_bytes, size = processor.process_image(img_data['url'])
            if img_bytes:
                filename = f"{keyword}-travel-{idx+1}-{random.randint(1000,9999)}.jpg"
                alt_text = f"{keyword} travel experience photo {idx+1}"
                
                airtable_url = processor.upload_to_airtable(
                    img_bytes, filename, alt_text, keyword
                )
                
                if airtable_url:
                    processed_images.append({
                        'url': airtable_url,
                        'alt': alt_text
                    })
        
        # 5. 이미지 HTML 생성
        images_html = "\n".join([
            f'<img src="{img["url"]}" alt="{img["alt"]}" class="travel-image">'
            for img in processed_images
        ])
        
        # 6. Make.com Webhook으로 전송
        webhook_data = {
            'title': f"Ultimate {keyword.title()} Travel Guide",
            'content': blog_post,
            'images_html': images_html,
            'full_content': f"{blog_post}\n\n<div class='image-gallery'>\n{images_html}\n</div>",
            'keyword': keyword,
            'status': 'draft',
            'processed_at': datetime.now().isoformat()
        }
        
        # Webhook 호출
        if MAKE_WEBHOOK_URL:
            requests.post(MAKE_WEBHOOK_URL, json=webhook_data)
        
        return jsonify({
            'success': True,
            'message': 'Blog processed successfully',
            'word_count': len(blog_post.split()),
            'images_processed': len(processed_images),
            'webhook_sent': bool(MAKE_WEBHOOK_URL)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """헬스체크 엔드포인트"""
    return jsonify({'status': 'healthy', 'service': 'blog-generator'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
