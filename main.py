# MoneyMaking_Crawler v3.3 - 디버그 버전 (단계별 테스트)
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

# Flask 라우트들
@app.route("/")
def home():
    return {
        "message": "💰 MoneyMaking_Crawler v3.3 - 디버그 버전",
        "status": "🔍 DEBUG MODE ACTIVE",
        "purpose": "단계별 디버깅으로 정확한 문제점 찾기",
        "debug_endpoints": {
            "step1": "/debug_step1 - 기본 연결 테스트",
            "step2": "/debug_step2 - Google 번역 테스트", 
            "step3": "/debug_step3 - Google 검색 테스트",
            "step4": "/debug_step4 - 블로그 필터링 테스트",
            "step5": "/debug_step5 - 전체 프로세스 단계별 실행"
        },
        "original_endpoints": {
            "home": "/",
            "test": "/test",
            "global_crawl": "/global_crawl"
        },
        "timestamp": datetime.utcnow().isoformat()
    }

@app.route("/debug_step1")
def debug_step1():
    """1단계: 기본 연결 및 파라미터 테스트"""
    try:
        result = {
            "step": "1 - 기본 연결 테스트",
            "timestamp": datetime.utcnow().isoformat(),
            "tests": {}
        }
        
        # 기본 파라미터 테스트
        keyword = request.args.get("keyword", "test")
        location = request.args.get("location", "test") 
        max_blogs = request.args.get("max_blogs", "1")
        
        result["tests"]["parameter_parsing"] = {
            "status": "SUCCESS",
            "keyword": keyword,
            "location": location, 
            "max_blogs": max_blogs
        }
        
        # Google 인증 상태 확인
        result["tests"]["google_auth"] = {
            "credentials": "✅ 있음" if credentials else "❌ 없음",
            "translate_client": "✅ 있음" if translate_client else "❌ 없음",
            "drive_service": "✅ 있음" if drive_service else "❌ 없음"
        }
        
        # 기본 HTTP 요청 테스트
        try:
            response = requests.get("https://httpbin.org/ip", timeout=10)
            result["tests"]["http_request"] = {
                "status": "SUCCESS",
                "status_code": response.status_code,
                "response_time": "< 10초"
            }
        except Exception as e:
            result["tests"]["http_request"] = {
                "status": "FAILED", 
                "error": str(e)
            }
        
        result["overall_status"] = "SUCCESS - 1단계 통과"
        return result
        
    except Exception as e:
        return {
            "step": "1 - 기본 연결 테스트",
            "status": "FAILED",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@app.route("/debug_step2")
def debug_step2():
    """2단계: Google 번역 API 테스트"""
    try:
        result = {
            "step": "2 - Google 번역 테스트",
            "timestamp": datetime.utcnow().isoformat(),
            "tests": {}
        }
        
        keyword = request.args.get("keyword", "cancun travel")
        
        # 번역 테스트
        if translate_client and credentials:
            try:
                parent = f"projects/{credentials.project_id}/locations/global"
                response = translate_client.translate_text(
                    request={
                        "parent": parent,
                        "contents": [keyword],
                        "mime_type": "text/plain",
                        "source_language_code": "en",
                        "target_language_code": "ja",
                    }
                )
                translated = response.translations[0].translated_text
                
                result["tests"]["translation"] = {
                    "status": "SUCCESS",
                    "original": keyword,
                    "translated": translated,
                    "target_lang": "ja"
                }
            except Exception as e:
                result["tests"]["translation"] = {
                    "status": "FAILED",
                    "error": str(e)
                }
        else:
            result["tests"]["translation"] = {
                "status": "SKIPPED",
                "reason": "번역 클라이언트 없음"
            }
        
        result["overall_status"] = "SUCCESS - 2단계 통과"
        return result
        
    except Exception as e:
        return {
            "step": "2 - Google 번역 테스트", 
            "status": "FAILED",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@app.route("/debug_step3")
def debug_step3():
    """3단계: Google 검색 연결 테스트"""
    try:
        result = {
            "step": "3 - Google 검색 테스트",
            "timestamp": datetime.utcnow().isoformat(),
            "tests": {}
        }
        
        keyword = request.args.get("keyword", "cancun travel")
        
        # 일본 Google에 간단한 검색 요청
        country_info = TARGET_COUNTRIES['japan']
        search_query = keyword
        encoded_query = quote_plus(search_query)
        search_url = f"https://www.{country_info['domain']}/search?q={encoded_query}&num=5"
        
        result["tests"]["search_url_generation"] = {
            "status": "SUCCESS",
            "search_url": search_url,
            "encoded_query": encoded_query
        }
        
        # HTTP 헤더 준비
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
        
        result["tests"]["headers"] = {
            "status": "SUCCESS",
            "user_agent": headers['User-Agent'][:50] + "..."
        }
        
        # 실제 Google 요청 (타임아웃 짧게)
        try:
            print(f"🔍 Google 검색 요청 시작: {search_url}")
            response = requests.get(search_url, headers=headers, timeout=15)
            
            result["tests"]["google_request"] = {
                "status": "SUCCESS" if response.status_code == 200 else "PARTIAL",
                "status_code": response.status_code,
                "response_size": len(response.text),
                "content_preview": response.text[:200] + "..." if response.text else "응답 없음"
            }
            
            # HTML 파싱 테스트
            if response.status_code == 200 and response.text:
                soup = BeautifulSoup(response.text, 'html.parser')
                search_results = soup.find_all('div', class_='g')
                
                result["tests"]["html_parsing"] = {
                    "status": "SUCCESS",
                    "results_found": len(search_results),
                    "sample_titles": []
                }
                
                # 샘플 결과 수집
                for i, result_div in enumerate(search_results[:3]):
                    try:
                        link = result_div.find('a', href=True)
                        title = result_div.find('h3')
                        if link and title:
                            result["tests"]["html_parsing"]["sample_titles"].append({
                                "title": title.get_text()[:50],
                                "url": link['href'][:50] + "..."
                            })
                    except:
                        continue
            else:
                result["tests"]["html_parsing"] = {
                    "status": "FAILED",
                    "reason": "응답이 없거나 상태 코드 오류"
                }
                
        except Exception as e:
            result["tests"]["google_request"] = {
                "status": "FAILED",
                "error": str(e),
                "error_type": type(e).__name__
            }
        
        result["overall_status"] = "SUCCESS - 3단계 통과" if result["tests"]["google_request"]["status"] == "SUCCESS" else "FAILED - 3단계 실패"
        return result
        
    except Exception as e:
        return {
            "step": "3 - Google 검색 테스트",
            "status": "FAILED", 
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@app.route("/debug_step4")
def debug_step4():
    """4단계: 개인 블로그 필터링 테스트"""
    try:
        result = {
            "step": "4 - 블로그 필터링 테스트",
            "timestamp": datetime.utcnow().isoformat(),
            "tests": {}
        }
        
        # 테스트용 URL들 (실제 블로그 + 기업 사이트)
        test_urls = [
            {
                "url": "https://myblogabouttravel.wordpress.com/cancun-adventure",
                "title": "My Amazing Cancun Travel Experience", 
                "description": "Personal blog about my incredible journey to Cancun",
                "expected": "PERSONAL"
            },
            {
                "url": "https://booking.com/hotels/cancun",
                "title": "Best Hotels in Cancun - Book Now",
                "description": "Find the best hotel deals in Cancun",
                "expected": "CORPORATE"
            },
            {
                "url": "https://medium.com/@traveler/cancun-guide",
                "title": "Ultimate Cancun Guide",
                "description": "A complete guide to visiting Cancun Mexico",
                "expected": "PERSONAL"
            }
        ]
        
        # 개인 블로그 판별 함수 (간단 버전)
        def is_personal_blog_simple(url, title, description):
            url_lower = url.lower()
            title_lower = title.lower() if title else ""
            desc_lower = description.lower() if description else ""
            
            # 기업 사이트 체크
            corporate_exclusions = ['booking.com', 'tripadvisor.com', 'expedia.com']
            for exclusion in corporate_exclusions:
                if exclusion in url_lower:
                    return False, f"기업 사이트: {exclusion}"
            
            # 개인 블로그 지표
            personal_indicators = ['blog', 'personal', 'my', 'experience', 'travel', 'journey']
            text_to_check = f"{url_lower} {title_lower} {desc_lower}"
            score = sum(1 for indicator in personal_indicators if indicator in text_to_check)
            
            return score >= 1, f"점수: {score}"
        
        # 각 테스트 URL 확인
        filter_results = []
        for test_case in test_urls:
            is_personal, reason = is_personal_blog_simple(
                test_case["url"], 
                test_case["title"], 
                test_case["description"]
            )
            
            result_type = "PERSONAL" if is_personal else "CORPORATE"
            is_correct = result_type == test_case["expected"]
            
            filter_results.append({
                "url": test_case["url"][:50] + "...",
                "title": test_case["title"],
                "expected": test_case["expected"],
                "actual": result_type,
                "correct": is_correct,
                "reason": reason
            })
        
        result["tests"]["filtering_accuracy"] = {
            "status": "SUCCESS",
            "test_cases": filter_results,
            "accuracy": f"{sum(1 for r in filter_results if r['correct'])}/{len(filter_results)}"
        }
        
        result["overall_status"] = "SUCCESS - 4단계 통과"
        return result
        
    except Exception as e:
        return {
            "step": "4 - 블로그 필터링 테스트",
            "status": "FAILED",
            "error": str(e), 
            "timestamp": datetime.utcnow().isoformat()
        }

@app.route("/debug_step5")
def debug_step5():
    """5단계: 전체 프로세스 단계별 실행 (1개국만)"""
    try:
        result = {
            "step": "5 - 전체 프로세스 테스트",
            "timestamp": datetime.utcnow().isoformat(),
            "progress": {}
        }
        
        keyword = request.args.get("keyword", "cancun travel")
        location = request.args.get("location", "Mexico")
        
        # 5-1: 파라미터 확인
        result["progress"]["5-1_parameters"] = {
            "status": "SUCCESS",
            "keyword": keyword,
            "location": location
        }
        
        # 5-2: 번역 테스트 (일본어로)
        if translate_client and credentials:
            try:
                parent = f"projects/{credentials.project_id}/locations/global"
                response = translate_client.translate_text(
                    request={
                        "parent": parent,
                        "contents": [keyword],
                        "mime_type": "text/plain",
                        "source_language_code": "en",
                        "target_language_code": "ja",
                    }
                )
                translated_keyword = response.translations[0].translated_text
                result["progress"]["5-2_translation"] = {
                    "status": "SUCCESS",
                    "translated": translated_keyword
                }
            except Exception as e:
                result["progress"]["5-2_translation"] = {
                    "status": "FAILED",
                    "error": str(e)
                }
                return result
        else:
            translated_keyword = keyword
            result["progress"]["5-2_translation"] = {
                "status": "SKIPPED",
                "reason": "번역 서비스 없음"
            }
        
        # 5-3: Google 검색 (일본만)
        try:
            country_info = TARGET_COUNTRIES['japan']
            encoded_query = quote_plus(translated_keyword)
            search_url = f"https://www.{country_info['domain']}/search?q={encoded_query}&num=10"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(search_url, headers=headers, timeout=20)
            
            result["progress"]["5-3_google_search"] = {
                "status": "SUCCESS" if response.status_code == 200 else "FAILED",
                "status_code": response.status_code,
                "search_url": search_url,
                "response_size": len(response.text) if response.text else 0
            }
            
            if response.status_code != 200:
                return result
                
        except Exception as e:
            result["progress"]["5-3_google_search"] = {
                "status": "FAILED",
                "error": str(e)
            }
            return result
        
        # 5-4: HTML 파싱 및 블로그 찾기
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            search_results = soup.find_all('div', class_='g')
            
            found_blogs = []
            for i, result_div in enumerate(search_results[:10]):
                try:
                    link_elem = result_div.find('a', href=True)
                    title_elem = result_div.find('h3')
                    
                    if link_elem and title_elem:
                        url = link_elem['href']
                        title = title_elem.get_text()
                        
                        # 간단한 개인 블로그 체크
                        if 'blog' in url.lower() or 'blog' in title.lower():
                            found_blogs.append({
                                "url": url[:50] + "...",
                                "title": title[:50] + "..."
                            })
                            
                        if len(found_blogs) >= 3:  # 최대 3개만
                            break
                            
                except Exception:
                    continue
            
            result["progress"]["5-4_blog_extraction"] = {
                "status": "SUCCESS",
                "total_results": len(search_results),
                "found_blogs": len(found_blogs),
                "sample_blogs": found_blogs
            }
            
        except Exception as e:
            result["progress"]["5-4_blog_extraction"] = {
                "status": "FAILED", 
                "error": str(e)
            }
            return result
        
        # 5-5: 최종 결과
        result["progress"]["5-5_final"] = {
            "status": "SUCCESS",
            "message": "전체 프로세스 완료",
            "ready_for_full_crawling": len(found_blogs) > 0
        }
        
        result["overall_status"] = "SUCCESS - 전체 프로세스 작동 확인"
        return result
        
    except Exception as e:
        return {
            "step": "5 - 전체 프로세스 테스트", 
            "status": "FAILED",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

# 기존 엔드포인트들도 유지
@app.route("/test")
def test():
    return {
        "message": "💰 MoneyMaking_Crawler v3.3 - 디버그 모드",
        "debug_mode": "ACTIVE",
        "available_debug_steps": [
            "/debug_step1 - 기본 연결",
            "/debug_step2 - 번역 API", 
            "/debug_step3 - Google 검색",
            "/debug_step4 - 블로그 필터링",
            "/debug_step5 - 전체 프로세스"
        ],
        "google_cloud": "✅ Connected" if credentials else "❌ Not Connected",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.route("/global_crawl", methods=['GET', 'POST'])
def global_crawl():
    """기존 global_crawl (참고용)"""
    return {
        "message": "디버그 모드에서는 /debug_step1~5를 사용하세요",
        "debug_endpoints": [
            "/debug_step1",
            "/debug_step2", 
            "/debug_step3",
            "/debug_step4",
            "/debug_step5"
        ],
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
