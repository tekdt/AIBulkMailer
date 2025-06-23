import smtplib
import pickle
import ssl
import csv
import time
import random
import json
import sys
import os
import requests
import http.cookiejar
import ctypes
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import msal
import re
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from openai import OpenAI
from mistralai import Mistral
import groq
import google.generativeai as genai
from bs4 import BeautifulSoup
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QLineEdit, QTextEdit, QProgressBar, QComboBox, QTabWidget, QCheckBox, QMessageBox
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import dns.resolver
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon, QIntValidator
from lxml import html
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

if hasattr(sys, "_MEIPASS"):  # Khi chạy từ bundle của PyInstaller
    icon_path = os.path.join(sys._MEIPASS, "logo.ico")
else:  # Khi chạy từ mã nguồn
    icon_path = "logo.ico"

version = "1.4.1"
released_date = "23/06/2025"
SETTINGS_FILE = "settings.json"
DEFAULT_SETTINGS = {
    "lm_url_default": "http://localhost:1234",
    "ollama_url_default": "http://localhost:11434",
    "SMTP_CONFIG": {
        "Gmail": {"server": "smtp.gmail.com", "port_ssl": 465, "port_tls": 587},
        "Yahoo": {"server": "smtp.mail.yahoo.com", "port_ssl": 465, "port_tls": 587},
        "Mailtrap": {"server": "live.smtp.mailtrap.io", "port_tls": 587},
        "AOL": {"server": "smtp.aol.com", "port_ssl": 465, "port_tls": 587},
        "Mailersend": {"server": "smtp.mailersend.net", "port_tls": 587},
        "Hotmail/Outlook": {"server": "smtp-mail.outlook.com", "port_ssl": 465, "port_tls": 587},
        "Yandex": {"server": "smtp.yandex.com", "port_ssl": 465, "port_tls": 587},
        "ZohoMail": {"server": "smtp.zoho.com", "port_ssl": 465, "port_tls": 587},
        "Proton": {"server": "smtp.protonmail.ch", "port_tls": 587
    }
},
    "AI_MODELS": {
        "ChatGPT": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4.5-preview", "o3-mini", "gpt-4o", "gpt-4o-mini", "whisper-1"],
        "Groq": ["distil-whisper-large-v3-en", "gemma2-9b-it", "llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama-guard-3-8b", "llama3-70b-8192", "llama3-8b-8192", "mixtral-8x7b-32768", "whisper-large-v3", "whisper-large-v3-turbo", "deepseek-r1-distill-qwen-32b", "deepseek-r1-distill-llama-70b-specdec", "qwen-qwq-32b", "mistral-saba-24b", "qwen-2.5-coder-32b", "qwen-2.5-32b", "deepseek-r1-distill-llama-70b", "llama-3.3-70b-specdec"],
        "Gemini": ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash", "gemini-1.5-flash-8b", "gemini-1.5-pro", "text-embedding-004"],
        "Grok": ["grok-2-1212", "grok-2-vision-1212"],
        "DeepSeek": ["deepseek-chat", "deepseek-reasoner", "deepseek-coder"],
        "Mistral": ["mistral-large-latest", "pixtral-large-latest", "mistral-moderation-latest", "ministral-3b-latest", "ministral-8b-latest", "open-mistral-nemo", "mistral-small-latest", "mistral-saba-latest", "codestral-latest", "mistral-ocr-latest"]
    }
}
global SMTP_CONFIG, AI_MODELS  # Định nghĩa biến toàn cục

# Hàm lấy token cho Gmail
def get_gmail_token(client_id, client_secret, refresh_token):
    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret
    )
    if creds.expired:
        creds.refresh(Request())
    return creds.token

# Hàm lấy token cho Outlook
def get_outlook_token(client_id, client_secret, refresh_token):
    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority="https://login.microsoftonline.com/common"
    )
    result = app.acquire_token_by_refresh_token(
        refresh_token=refresh_token,
        scopes=["https://outlook.office.com/SMTP.Send"]
    )
    return result.get("access_token")

class SMTP_OAUTH(smtplib.SMTP):
    def login(self, user, token):
        """Xác thực với máy chủ SMTP bằng OAuth2 token."""
        auth_string = f"user={user}\x01auth=Bearer {token}\x01\x01"
        auth_msg = base64.b64encode(auth_string.encode()).decode()
        code, message = self.docmd("AUTH", "XOAUTH2 " + auth_msg)
        if code != 235:
            raise smtplib.SMTPAuthenticationError(code, message)

class EmailSenderWorker(QObject):
    success_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    summary_signal = pyqtSignal(dict)

    def __init__(self, parent, smtp_server, port, sender_email, password, subject, body, recipients, connection_security, reply_to=None, cc=None, bcc=None, use_oauth=False, oauth_config=None, refresh_token=None, auto_integration=False, ai_server=None, api_key=None, ai_prompt=None, model=None, min_delay=None, max_delay=None, local_ai_url=None):
        super().__init__()
        self.parent = parent  # Lưu widget cha
        self.smtp_server = smtp_server
        self.port = port
        self.sender_email = sender_email
        self.password = password
        self.subject = subject
        self.body = body
        self.recipients = list(recipients)  # Tạo bản sao của danh sách recipients
        self.reply_to = reply_to
        self.cc = cc
        self.bcc = bcc
        self.connection_security = connection_security
        self.use_oauth = use_oauth
        self.oauth_config = oauth_config
        self.refresh_token = refresh_token
        self.is_sending = False
        self.should_stop = False
        self.auto_integration = auto_integration
        self.ai_server = ai_server
        self.api_key = api_key
        self.ai_prompt = ai_prompt
        self.model = model
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.local_ai_url = local_ai_url

    def stop(self):
        """Đặt cờ để dừng quá trình gửi email"""
        self.should_stop = True
        self.error_signal.emit("⛔ Đang dừng...")    
    
    def remove_think_tags(self, content):
        """Xóa toàn bộ nội dung nằm trong thẻ <think>...</think>"""
        return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    
    def generate_unique_content(self, recipient):
        # Tạo prompt riêng cho từng người nhận để đảm bảo nội dung khác nhau
        prompt = f"{self.ai_prompt}"
        try:
            if self.ai_server == "ChatGPT":
                response = openai.ChatCompletion.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}]
                )
                raw_content = response.choices[0].message.content
                cleaned_content = self.remove_think_tags(raw_content)  # Xóa phần <think>
                cleaned_content = re.sub(r"^```(?:html)?\n?|```$", "", cleaned_content, flags=re.MULTILINE)  # Loại bỏ dấu ```
                return cleaned_content.strip()  # Loại bỏ khoảng trắng thừa
            elif self.ai_server == "LM Studio":
                if not self.local_ai_url:
                    self.error_signal.emit("Lỗi AI: URL cho LM Studio không được cung cấp.")
                    return self.body # Trả về body mặc định
                
                # Sử dụng URL đã được truyền vào
                url = self.local_ai_url.rstrip("/") + "/v1/chat/completions"
                headers = {"Content-Type": "application/json"}
                data = {
                    "model": self.model,
                    "messages": [{"role": "system", "content": self.prompt}],
                    "max_tokens": 4096  # Điều chỉnh theo nhu cầu
                }
                response = requests.post(url, headers=headers, json=data, timeout=300)
                if response.status_code != 200:
                    print(f"Lỗi từ server: {response.status_code} - {response.text}")
                    error_msg = f"Lỗi từ server: {response.status_code} - {response.text}"
                    self.error_signal.emit(error_msg) # Phát tín hiệu lỗi cho giao diện
                    QThread.currentThread().quit()
                    return self.body
                response_data = response.json()
                raw_content = response_data["choices"][0]["message"]["content"]
                cleaned_content = self.remove_think_tags(raw_content)  # Xóa phần <think>
                cleaned_content = re.sub(r"^```(?:html)?\n?|```$", "", cleaned_content, flags=re.MULTILINE)  # Loại bỏ dấu ```
                return cleaned_content.strip()  # Loại bỏ khoảng trắng thừa
            elif self.ai_server == "Ollama":
                if not self.local_ai_url:
                    self.error_signal.emit("Lỗi AI: URL cho Ollama không được cung cấp.")
                    return self.body
                
                # Sử dụng URL đã được truyền vào
                base_url = self.local_ai_url.rstrip("/") + "/v1/"
                client = OpenAI(api_key='ollama', base_url=base_url)
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    stream=False
                )
                raw_content = response.choices[0].message.content
                cleaned_content = self.remove_think_tags(raw_content)  # Xóa phần <think>
                cleaned_content = re.sub(r"^```(?:html)?\n?|```$", "", cleaned_content, flags=re.MULTILINE)  # Loại bỏ dấu ```
                return cleaned_content.strip()  # Loại bỏ khoảng trắng thừa
            elif self.ai_server == "Gemini":
                genai.configure(api_key=self.api_key)
                model_obj = genai.GenerativeModel(self.model)
                response = model_obj.generate_content(prompt)
                raw_content = response.text
                cleaned_content = self.remove_think_tags(raw_content)  # Xóa phần <think>
                cleaned_content = re.sub(r"^```(?:html)?\n?|```$", "", cleaned_content, flags=re.MULTILINE)  # Loại bỏ dấu ```
                return cleaned_content.strip()  # Loại bỏ khoảng trắng thừa
            elif self.ai_server == "Groq":
                client = groq.Client(api_key=self.api_key)
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}]
                )
                raw_content = response.choices[0].message.content
                cleaned_content = self.remove_think_tags(raw_content)  # Xóa phần <think> cho nội dung trả về từ mô hình DeepSeek
                cleaned_content = re.sub(r"^```(?:html)?\n?|```$", "", cleaned_content, flags=re.MULTILINE)  # Loại bỏ dấu ```
                return cleaned_content.strip()  # Loại bỏ khoảng trắng thừa
            elif self.ai_server == "DeepSeek":
                client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    stream=False
                )
                raw_content = response.choices[0].message.content
                cleaned_content = self.remove_think_tags(raw_content)  # Xóa phần <think>
                cleaned_content = re.sub(r"^```(?:html)?\n?|```$", "", cleaned_content, flags=re.MULTILINE)  # Loại bỏ dấu ```
                return cleaned_content.strip()  # Loại bỏ khoảng trắng thừa
            elif self.ai_server == "Mistral":
                client = Mistral(api_key=self.api_key)
                response = client.chat.complete(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw_content = response.choices[0].message.content
                cleaned_content = self.remove_think_tags(raw_content)  # Xóa phần <think>
                cleaned_content = re.sub(r"^```(?:html)?\n?|```$", "", cleaned_content, flags=re.MULTILINE)  # Loại bỏ dấu ```
                return cleaned_content.strip()  # Loại bỏ khoảng trắng thừa
            elif self.ai_server == "Grok":
                return "Grok chưa có API công khai, hãy kiểm tra sau!"
            else:
                return self.body  # Fallback
        except requests.exceptions.Timeout:
            self.error_signal.emit("❌ Hết thời gian chờ khi kết nối đến {ai_server}. Vui lòng kiểm tra máy chủ.")
            return self.body
        except requests.exceptions.ConnectionError:
            self.error_signal.emit("❌ Không thể kết nối đến {ai_server}. Vui lòng kiểm tra URL và kết nối mạng.")
            return self.body
        except requests.exceptions.HTTPError as e:
            self.error_signal.emit(f"❌ Lỗi HTTP từ {ai_server}: {str(e)}")
            return self.body
        except json.JSONDecodeError:
            self.error_signal.emit("❌ Phản hồi từ {ai_server} không phải JSON hợp lệ.")
            return self.body
        except KeyError:
            self.error_signal.emit("❌ Không tìm thấy key 'choices' trong phản hồi từ {ai_server}.")
            return self.body
        except Exception as e:
            self.error_signal.emit(f"❌ Lỗi không xác định: {str(e)}")
            return self.body
    
    def run(self):
        failures = {}
        successes = 0
        try:
            start_time = time.time()
            context = ssl.create_default_context()                
                
            # Chọn kiểu kết nối và xác thực dựa trên use_oauth
            if self.use_oauth:
                # Lấy token OAuth2 dựa trên nhà cung cấp
                provider = self.oauth_config.get("provider", "").lower()
                if provider == "gmail":
                    token = get_gmail_token(self.oauth_config["client_id"], self.oauth_config["client_secret"], self.refresh_token)
                    server = SMTP_OAUTH(self.smtp_server, self.port)
                elif provider == "outlook":
                    token = get_outlook_token(self.oauth_config["client_id"], self.oauth_config["client_secret"], self.refresh_token)
                    server = SMTP_OAUTH(self.smtp_server, self.port)
                else:
                    raise ValueError("Nhà cung cấp OAuth2 không được hỗ trợ.")
                
                # Kết nối SSL hoặc TLS nếu cần
                if self.connection_security == "SSL":
                    server = SMTP_OAUTH(self.smtp_server, self.port, context=context)
                elif self.connection_security == "TLS":
                    server = SMTP_OAUTH(self.smtp_server, self.port)
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                
                # Đăng nhập bằng OAuth2
                try:
                    server.login(self.sender_email, token)
                except smtplib.SMTPAuthenticationError:
                    self.error_signal.emit("❌ Xác thực OAuth2 thất bại: Kiểm tra client_id, client_secret, và refresh_token")
                    return
            else:
                # Xác thực truyền thống
                if self.connection_security == "SSL":
                    server = smtplib.SMTP_SSL(self.smtp_server, self.port, context=context, timeout=30)
                elif self.connection_security == "TLS":
                    server = smtplib.SMTP(self.smtp_server, self.port, timeout=30)
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                else:
                    server = smtplib.SMTP(self.smtp_server, self.port, timeout=30)
                
                # Đăng nhập bằng email và mật khẩu
                try:
                    server.login(self.sender_email, self.password)
                except smtplib.SMTPAuthenticationError:
                    self.error_signal.emit("❌ Xác thực thất bại: Kiểm tra email và mật khẩu")
                    return

            # Gửi email đến từng người nhận
            for idx, recipient in enumerate(self.recipients):
                self.log_signal.emit(f"Đang gửi email thứ {idx+1}/{len(self.recipients)} đến {recipient}")
                if self.should_stop:
                    self.error_signal.emit("⛔ Quá trình gửi email đã bị dừng.")
                    if hasattr(self, "server") and self.server:
                        self.server.quit()
                    return
                    
                # Kiểm tra xem kết nối còn sống không
                try:
                    status = server.noop()[0]  # Trả về mã trạng thái, 250 là thành công
                except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError):
                    status = None
                if status != 250:
                    self.log_signal.emit(f"⚠️ Kết nối bị ngắt trước khi gửi email thứ {idx+1}, đang kết nối lại...")
                    try:
                        if self.connection_security == "SSL":
                            server = smtplib.SMTP_SSL(self.smtp_server, self.port, context=context, timeout=30)
                        elif self.connection_security == "TLS":
                            server = smtplib.SMTP(self.smtp_server, self.port, timeout=30)
                            server.ehlo()
                            server.starttls(context=context)
                            server.ehlo()
                        else:
                            server = smtplib.SMTP(self.smtp_server, self.port, timeout=30)
                        if self.use_oauth:
                            token = get_gmail_token(self.oauth_config["client_id"], self.oauth_config["client_secret"], self.refresh_token) if self.oauth_config.get("provider") == "gmail" else get_outlook_token(self.oauth_config["client_id"], self.oauth_config["client_secret"], self.refresh_token)
                            server.login(self.sender_email, token)
                        else:
                            server.login(self.sender_email, self.password)
                    except Exception as e:
                        self.error_signal.emit(f"❌ Không thể kết nối lại server: {str(e)}")
                        return

                # Nếu auto_integration được bật, tạo nội dung mới cho mỗi email
                if self.auto_integration:
                    unique_body = self.generate_unique_content(recipient)
                    # **Kiểm tra nội dung trước khi gửi**
                    if not unique_body or not self.is_valid_content(unique_body):
                        self.log_signal.emit(f"⚠️ Nội dung không hợp lệ cho {recipient}, không gửi email.")
                        continue
                else:
                    unique_body = self.body
                   
                # Thử gửi email tối đa 3 lần
                for attempt in range(3):
                    try:
                        msg = MIMEMultipart()
                        msg['From'] = self.sender_email
                        msg['To'] = recipient
                        msg['Subject'] = self.subject
                        msg['Cc'] = self.cc
                        all_recipients = [recipient]
                        # Xử lý CC
                        if self.cc:
                            cc_list = [email.strip() for email in self.cc.split(",") if email.strip()]
                            all_recipients += cc_list

                        # Xử lý BCC
                        if self.bcc:
                            bcc_list = [email.strip() for email in self.bcc.split(",") if email.strip()]
                            all_recipients += bcc_list

                        if self.reply_to:
                            msg['Reply-To'] = self.reply_to
                        msg.attach(MIMEText(unique_body, 'html'))
                        # server.sendmail(self.sender_email, recipient, msg.as_string())
                        server.sendmail(self.sender_email, all_recipients, msg.as_string())
                        successes += 1
                        # Phát tín hiệu ngay khi gửi thành công
                        self.success_signal.emit(recipient)
                        self.log_signal.emit(f"✅ Email được gửi tới {recipient}")
                        break  # Thoát vòng lặp nếu gửi thành công
                    except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError) as e:
                        if attempt < 2:  # Thử lại nếu chưa đủ 3 lần
                            self.log_signal.emit(f"⚠️ Lỗi khi gửi tới {recipient}: {str(e)}. Thử lại lần {attempt + 2}...")
                            time.sleep(5)  # Chờ 5 giây trước khi thử lại
                            # Thử kết nối lại server nếu bị ngắt
                            try:
                                if self.connection_security == "SSL":
                                    server = smtplib.SMTP_SSL(self.smtp_server, self.port, context=context, timeout=30)
                                elif self.connection_security == "TLS":
                                    server = smtplib.SMTP(self.smtp_server, self.port, timeout=30)
                                    server.ehlo()
                                    server.starttls(context=context)
                                    server.ehlo()
                                else:
                                    server = smtplib.SMTP(self.smtp_server, self.port, timeout=30)
                                if self.use_oauth:
                                    token = get_gmail_token(self.oauth_config["client_id"], self.oauth_config["client_secret"], self.refresh_token) if self.oauth_config.get("provider") == "gmail" else get_outlook_token(self.oauth_config["client_id"], self.oauth_config["client_secret"], self.refresh_token)
                                    server.login(self.sender_email, token)
                                else:
                                    server.login(self.sender_email, self.password)
                            except Exception as reconnect_error:
                                self.log_signal.emit(f"❌ Lỗi khi kết nối lại server: {str(reconnect_error)}")
                        else:
                            failures[recipient] = str(e)
                            self.log_signal.emit(f"❌ Gửi mail không thành công tới {recipient} sau 3 lần thử: {str(e)}")
                    except smtplib.SMTPException as e:
                        error_message = str(e)
                        if "please run connect() first" in error_message.lower():
                            self.error_signal.emit("❌ Lỗi: Máy chủ yêu cầu kết nối trước khi gửi email. Hãy thử lại sau.")
                            return
                        if "unusual sending activity" in error_message.lower():
                            self.error_signal.emit("⚠️ Cảnh báo: Hoạt động gửi mail bất thường! Chương trình dừng để tránh bị đánh spam.")
                            return
                        if "rejected under suspicion" in error_message.lower():
                            self.error_signal.emit("⚠️ Cảnh báo: Hoạt động gửi mail bị từ chối! Chương trình dừng để tránh bị đánh spam.")
                            return
                        failures[recipient] = error_message
                        self.log_signal.emit(f"❌ Gửi mail không thành công tới {recipient}: {error_message}")
                        break  # Không thử lại với các lỗi khác

                # Thời gian chờ ngẫu nhiên giữa các email
                if idx < len(self.recipients) - 1:  # Chỉ delay nếu còn email để gửi
                    delay_time = random.uniform(self.min_delay, self.max_delay)
                    self.log_signal.emit(f"⏳ Đang chờ {delay_time:.2f} giây trước khi gửi mail tiếp theo...")
                    for _ in range(int(delay_time * 10)):
                        if self.should_stop:
                            self.error_signal.emit("⛔ Quá trình gửi email đã bị dừng.")
                            if hasattr(self, "server") and self.server:
                                self.server.quit()
                            return
                        QThread.msleep(100)

                self.progress_signal.emit(idx + 1)
                
            server.quit()

            summary = {
                "total": len(self.recipients),
                "success": successes,
                "failed": len(failures),
                "failed_recipients": failures
            }
            self.summary_signal.emit(summary)
        except smtplib.SMTPAuthenticationError:
            self.error_signal.emit("❌ Xác thực thất bại. Vui lòng kiểm tra email và mật khẩu.")
        except smtplib.SMTPConnectError:
            self.error_signal.emit("❌ Không thể kết nối tới server SMTP. Kiểm tra server và port.")
        except Exception as e:
            self.error_signal.emit(f"❌ Đã xảy ra lỗi: {str(e)}")
        finally:
            pass
            
    def is_valid_content(self, content):
        """Kiểm tra nội dung có hợp lệ để gửi không"""
        if not content.strip():
            return False
        return True  # Có thể thêm các điều kiện khác nếu cần
    
def closeEvent(self, event):
    self.save_settings()
    if self.thread and self.thread.isRunning():
        self.thread.quit()
        self.thread.wait()
        self.thread.deleteLater()
        self.thread = None
    if self.gen_thread and self.gen_thread.isRunning():
        self.gen_thread.quit()
        self.gen_thread.wait()
        self.gen_thread.deleteLater()
        self.gen_thread = None
    event.accept()

class ContentGeneratorWorker(QObject):
    result_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, ai_server, api_key, prompt, model, local_ai_url=None):
        super().__init__()
        # self.parent = parent  # Lưu widget cha
        self.ai_server = ai_server
        self.api_key = api_key
        self.prompt = prompt
        self.model = model
        self.local_ai_url = local_ai_url  # Lưu URL được truyền vào
    
    def remove_think_tags(self, content):
        """Xóa toàn bộ nội dung nằm trong thẻ <think>...</think>"""
        return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    
    def run(self):
        try:
            if self.ai_server == "ChatGPT":
                client = OpenAI(api_key=self.api_key)
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": self.prompt}]
                )
                raw_content = response.choices[0].message.content
                cleaned_content = self.remove_think_tags(raw_content)  # Xóa phần <think>
                cleaned_content = re.sub(r"^```(?:html)?\n?|```$", "", cleaned_content, flags=re.MULTILINE)  # Loại bỏ dấu ```
                generated = cleaned_content.strip()  # Loại bỏ khoảng trắng thừa
            elif self.ai_server == "LM Studio":
                if not self.local_ai_url:
                    self.error_signal.emit("URL cho LM Studio không được cung cấp.")
                    return
                # Sử dụng URL đã được truyền vào, không truy cập GUI
                url = self.local_ai_url.rstrip("/") + "/v1/chat/completions"
                headers = {"Content-Type": "application/json"}
                data = {
                    "model": self.model,
                    "messages": [{"role": "system", "content": self.prompt}],
                    "max_tokens": 4096  # Điều chỉnh theo nhu cầu
                }
                response = requests.post(url, headers=headers, json=data, timeout=300)
                if response.status_code != 200:
                    print(f"Lỗi từ server: {response.status_code} - {response.text}")
                    return
                response_data = response.json()
                raw_content = response_data["choices"][0]["message"]["content"]
                cleaned_content = self.remove_think_tags(raw_content)  # Xóa phần <think>
                cleaned_content = re.sub(r"^```(?:html)?\n?|```$", "", cleaned_content, flags=re.MULTILINE)  # Loại bỏ dấu ```
                generated = cleaned_content.strip()  # Loại bỏ khoảng trắng thừa
            elif self.ai_server == "Ollama":
                if not self.local_ai_url:
                    self.error_signal.emit("URL cho Ollama không được cung cấp.")
                    return
                # Sử dụng URL đã được truyền vào
                base_url = self.local_ai_url.rstrip("/") + "/v1/"
                client = OpenAI(api_key='ollama', base_url=base_url)
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": self.prompt}],
                    stream=False
                )
                raw_content = response.choices[0].message.content
                cleaned_content = self.remove_think_tags(raw_content)  # Xóa phần <think>
                cleaned_content = re.sub(r"^```(?:html)?\n?|```$", "", cleaned_content, flags=re.MULTILINE)  # Loại bỏ dấu ```
                generated = cleaned_content.strip()  # Loại bỏ khoảng trắng thừa
            elif self.ai_server == "Gemini":
                genai.configure(api_key=self.api_key)
                model = genai.GenerativeModel(self.model)
                response = model.generate_content(self.prompt)
                raw_content = response.text
                cleaned_content = self.remove_think_tags(raw_content)  # Xóa phần <think>
                cleaned_content = re.sub(r"^```(?:html)?\n?|```$", "", cleaned_content, flags=re.MULTILINE)  # Loại bỏ dấu ```
                generated = cleaned_content.strip()  # Loại bỏ khoảng trắng thừa
            elif self.ai_server == "Groq":
                client = groq.Client(api_key=self.api_key)
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": self.prompt}]
                )
                raw_content = response.choices[0].message.content
                cleaned_content = self.remove_think_tags(raw_content)  # Xóa phần <think>
                cleaned_content = re.sub(r"^```(?:html)?\n?|```$", "", cleaned_content, flags=re.MULTILINE)  # Loại bỏ dấu ```
                generated = cleaned_content.strip()  # Loại bỏ khoảng trắng thừa
            elif self.ai_server == "DeepSeek":
                client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": self.prompt}],
                    stream=False
                )
                raw_content = response.choices[0].message.content
                cleaned_content = self.remove_think_tags(raw_content)  # Xóa phần <think>
                cleaned_content = re.sub(r"^```(?:html)?\n?|```$", "", cleaned_content, flags=re.MULTILINE)  # Loại bỏ dấu ```
                generated = cleaned_content.strip()  # Loại bỏ khoảng trắng thừa
            elif self.ai_server == "Mistral":
                client = Mistral(api_key=self.api_key)
                response = client.chat.complete(
                    model=self.model,
                    messages=[{"role": "user", "content": self.prompt}]
                )
                raw_content = response.choices[0].message.content
                cleaned_content = self.remove_think_tags(raw_content)  # Xóa phần <think>
                cleaned_content = re.sub(r"^```(?:html)?\n?|```$", "", cleaned_content, flags=re.MULTILINE)  # Loại bỏ dấu ```
                generated = cleaned_content.strip()  # Loại bỏ khoảng trắng thừa
            elif self.ai_server == "Grok":
                # Chưa có API chính thức từ xAI, cần cập nhật sau
                generated = "Grok chưa có API công khai, hãy kiểm tra sau!"
            else:
                # Xử lý các máy chủ AI khác (Groq, Gemini, v.v.) tại đây
                generated = "Đây là nội dung email được tạo tự động (mô phỏng). Không nên áp dụng vào nội dung mail của bạn."  # Giữ mô phỏng cho các trường hợp khác
            
            # **Điều kiện 1: Kiểm tra nội dung có rỗng không**
            if not generated.strip():
                self.error_signal.emit("Nội dung rỗng")
                return

            # **Điều kiện 2: Kiểm tra từ khóa cấm**
            if self.contains_banned_words(generated):
                self.error_signal.emit("Nội dung chứa từ cấm")
                return

            # **Điều kiện 3: Kiểm tra định dạng HTML (nếu nội dung là HTML)**
            if not self.is_valid_html(generated):
                self.error_signal.emit("HTML không hợp lệ")
                return
            
            self.result_signal.emit(generated)
            
        except requests.exceptions.Timeout:
            self.error_signal.emit("❌ Hết thời gian chờ khi kết nối đến {self.ai_server}. Vui lòng kiểm tra máy chủ.")
        except requests.exceptions.ConnectionError:
            self.error_signal.emit("❌ Không thể kết nối đến {self.ai_server}. Vui lòng kiểm tra URL và kết nối mạng.")
        except requests.exceptions.HTTPError as e:
            self.error_signal.emit(f"❌ Lỗi HTTP từ {self.ai_server}: {str(e)}")
        except json.JSONDecodeError:
            self.error_signal.emit("❌ Phản hồi từ {self.ai_server} không phải JSON hợp lệ.")
        except KeyError:
            self.error_signal.emit("❌ Không tìm thấy key 'choices' trong phản hồi từ {self.ai_server}.")
        except Exception as e:
            self.error_signal.emit(f"❌ Lỗi không xác định: {str(e)}")
        finally:
            QThread.currentThread().quit()  # Đảm bảo luồng dừng an toàn
            
    def is_valid_html(self, html):
        """Kiểm tra xem chuỗi có phải là HTML hợp lệ không"""
        try:
            BeautifulSoup(html, 'html.parser')
            return True
        except:
            return False

    def contains_banned_words(self, text):
        """Kiểm tra xem nội dung có chứa từ cấm không"""
        banned_words = ['lỗi', 'không hợp lệ', 'xin lỗi', 'error', 'sorry', 'invalid']  # Danh sách từ cấm, có thể tùy chỉnh
        for word in banned_words:
            if word.lower() in text.lower():
                return True
        return False

# ---------------- Main Application ---------------- #
class BulkEmailSender(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Window)
        self.SMTP_CONFIG = DEFAULT_SETTINGS["SMTP_CONFIG"]
        self.AI_MODELS = DEFAULT_SETTINGS["AI_MODELS"]
        self.lm_url = "http://localhost:1234"
        self.ollama_url = "http://localhost:11434"
        self.initUI()
        self.load_settings()
        self.is_sending = False
        self.is_gathering = False
        self.extracted_emails = set()
        self.recipients_sent = []  # Danh sách email đã gửi thành công
        self._save_timer = QTimer(self)  # Khởi tạo timer với parent là self
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self.save_settings)
        # Gọi delayed_save_settings() mỗi khi người dùng nhập dữ liệu
        self.email_input.textChanged.connect(self.delayed_save_settings)
        self.password_input.textChanged.connect(self.delayed_save_settings)
        self.subject_input.textChanged.connect(self.delayed_save_settings)
        self.reply_input.textChanged.connect(self.delayed_save_settings)
        self.cc_input.textChanged.connect(self.delayed_save_settings)
        self.bcc_input.textChanged.connect(self.delayed_save_settings)
        self.provider_combo.currentIndexChanged.connect(self.delayed_save_settings)
        self.custom_smtp_input.textChanged.connect(self.delayed_save_settings)
        self.custom_port_input.textChanged.connect(self.delayed_save_settings)
        self.rich_editor.textChanged.connect(self.delayed_save_settings)
        self.raw_editor.textChanged.connect(self.delayed_save_settings)
        self.min_delay_input.textChanged.connect(self.delayed_save_settings)
        self.max_delay_input.textChanged.connect(self.delayed_save_settings)
        self.ai_server_combo.currentIndexChanged.connect(self.delayed_save_settings)
        self.ai_server_combo.currentIndexChanged.connect(self.update_model_combo)
        self.oauth_checkbox.stateChanged.connect(self.delayed_save_settings)
        self.client_id_input.textChanged.connect(self.delayed_save_settings)
        self.client_secret_input.textChanged.connect(self.delayed_save_settings)
        self.refresh_token_input.textChanged.connect(self.delayed_save_settings)
        self.api_key_input.textChanged.connect(self.delayed_save_settings)
        self.prompt_input.textChanged.connect(self.delayed_save_settings)
        self.generated_output.textChanged.connect(self.delayed_save_settings)
        self.auto_integration_checkbox.stateChanged.connect(self.delayed_save_settings)
        self.security_combo.currentIndexChanged.connect(self.delayed_save_settings)
        self.check_email_checkbox.stateChanged.connect(self.delayed_save_settings)
        self.url_input.textChanged.connect(self.delayed_save_settings)
        self.sitemap_checkbox.stateChanged.connect(self.delayed_save_settings)
        self.thread_count_input.textChanged.connect(self.delayed_save_settings)
        self.local_ai_url_input.textChanged.connect(self.delayed_save_settings)

    def initUI(self):
        self.tabs = QTabWidget()
        
        # -------- Tab MAIN -------- #
        self.main_tab = QWidget()
        main_layout = QVBoxLayout()

        # Row 1: Email và Password
        row1 = QHBoxLayout()
        self.email_label = QLabel("Email của bạn:")
        self.email_input = QLineEdit()
        self.email_input.textChanged.connect(self.update_smtp_provider)  # Thêm sự kiện
        row1.addWidget(self.email_label)
        row1.addWidget(self.email_input)
        self.password_label = QLabel("Mật khẩu:")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        row1.addWidget(self.password_label)
        row1.addWidget(self.password_input)
        main_layout.addLayout(row1)

        # Row 2: Subject
        row2 = QHBoxLayout()
        self.subject_label = QLabel("Tiêu đề:")
        self.subject_input = QLineEdit()
        row2.addWidget(self.subject_label)
        row2.addWidget(self.subject_input)
        main_layout.addLayout(row2)
        
        # Row for CC & BCC
        row_cc_bcc = QHBoxLayout()
        self.cc_label = QLabel("CC:")
        self.cc_input = QLineEdit()
        row_cc_bcc.addWidget(self.cc_label)
        row_cc_bcc.addWidget(self.cc_input)
        self.bcc_label = QLabel("BCC:")
        self.bcc_input = QLineEdit()
        row_cc_bcc.addWidget(self.bcc_label)
        row_cc_bcc.addWidget(self.bcc_input)
        main_layout.addLayout(row_cc_bcc)
        
        # Row 3: Reply-To
        row_reply = QHBoxLayout()
        self.reply_label = QLabel("Trả lời tới:")
        self.reply_input = QLineEdit()
        row_reply.addWidget(self.reply_label)
        row_reply.addWidget(self.reply_input)
        main_layout.addLayout(row_reply)

        # Row 4: Email Body
        self.body_label = QLabel("Nội dung Email (HTML):")
        main_layout.addWidget(self.body_label)
        self.tab_widget = QTabWidget()
        self.rich_editor = QTextEdit()
        self.rich_editor.setAcceptRichText(True)
        self.tab_widget.addTab(self.rich_editor, "Soạn thảo trực quan")
        self.raw_editor = QTextEdit()
        self.raw_editor.setAcceptRichText(False)
        self.tab_widget.addTab(self.raw_editor, "RAW HTML")
        self.tab_widget.currentChanged.connect(self.tab_changed)
        self.tab_widget.setMinimumHeight(300)
        main_layout.addWidget(self.tab_widget)

        # Row 5: SMTP Provider
        row3 = QHBoxLayout()
        self.provider_label = QLabel("Máy chủ SMTP:")
        row3.addWidget(self.provider_label)
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(list(self.SMTP_CONFIG.keys()) + ["Khác"])
        self.provider_combo.currentIndexChanged.connect(self.provider_changed)
        row3.addWidget(self.provider_combo)
        self.custom_smtp_label = QLabel("SMTP tuỳ chỉnh:")
        self.custom_smtp_input = QLineEdit()
        self.custom_port_label = QLabel("Cổng:")
        self.custom_port_input = QLineEdit()
        self.custom_smtp_label.setVisible(False)
        self.custom_smtp_input.setVisible(False)
        self.custom_port_label.setVisible(False)
        self.custom_port_input.setVisible(False)
        row3.addWidget(self.custom_smtp_label)
        row3.addWidget(self.custom_smtp_input)
        row3.addWidget(self.custom_port_label)
        row3.addWidget(self.custom_port_input)
        main_layout.addLayout(row3)
        
        # Thêm ô chọn Connection Security
        row_security = QHBoxLayout()
        self.security_label = QLabel("Kết nối Bảo mật:")
        row_security.addWidget(self.security_label)
        self.security_combo = QComboBox()
        self.security_combo.addItems(["SSL", "TLS", "None"])
        # Đặt mặc định là SSL (hoặc bạn có thể chọn khác)
        self.security_combo.setCurrentText("SSL")
        row_security.addWidget(self.security_combo)
        main_layout.addLayout(row_security)
        
        # Thêm checkbox và các trường OAuth2
        row_oauth = QHBoxLayout()
        self.oauth_checkbox = QCheckBox("Sử dụng OAuth2")
        self.oauth_checkbox.stateChanged.connect(self.toggle_oauth_fields)
        row_oauth.addWidget(self.oauth_checkbox)
        self.client_id_label = QLabel("Client ID:")
        self.client_id_input = QLineEdit()
        self.client_id_label.setVisible(False)
        self.client_id_input.setVisible(False)
        row_oauth.addWidget(self.client_id_label)
        row_oauth.addWidget(self.client_id_input)
        self.client_secret_label = QLabel("Client Secret:")
        self.client_secret_input = QLineEdit()
        self.client_secret_label.setVisible(False)
        self.client_secret_input.setVisible(False)
        row_oauth.addWidget(self.client_secret_label)
        row_oauth.addWidget(self.client_secret_input)
        self.refresh_token_label = QLabel("Refresh Token:")
        self.refresh_token_input = QLineEdit()
        self.refresh_token_label.setVisible(False)
        self.refresh_token_input.setVisible(False)
        row_oauth.addWidget(self.refresh_token_label)
        row_oauth.addWidget(self.refresh_token_input)
        main_layout.addLayout(row_oauth)

        # Row 6: Nút Load CSV & Send Emails
        row4 = QHBoxLayout()
        self.file_button = QPushButton("Tải danh sách người nhận (CSV)")
        self.file_button.clicked.connect(self.load_csv)
        row4.addWidget(self.file_button)
        self.min_delay_label = QLabel("Chờ từ")
        row4.addWidget(self.min_delay_label)
        self.min_delay_input = QLineEdit("120")
        self.min_delay_input.setValidator(QIntValidator())
        self.min_delay_input.setPlaceholderText("Chỉ nhập số nguyên")
        row4.addWidget(self.min_delay_input)
        self.max_delay_label = QLabel("tới")
        row4.addWidget(self.max_delay_label)
        self.max_delay_input = QLineEdit("300")
        self.max_delay_input.setValidator(QIntValidator())
        self.max_delay_input.setPlaceholderText("Chỉ nhập số nguyên")
        row4.addWidget(self.max_delay_input)
        self.sencond_sendmail_label = QLabel("giây, trước khi gửi mỗi mail")
        row4.addWidget(self.sencond_sendmail_label)
        self.send_button = QPushButton("Gửi mail")
        self.send_button.clicked.connect(self.send_emails)
        row4.addWidget(self.send_button)
        self.stop_sending_button = QPushButton("Dừng")
        self.stop_sending_button.clicked.connect(self.stop_sending)
        self.stop_sending_button.setEnabled(False)  # Ban đầu vô hiệu hóa
        row4.addWidget(self.stop_sending_button)
        main_layout.addLayout(row4)
        
        # Thêm ô tick kiểm tra email trước khi gửi (nếu bỏ chọn sẽ bỏ qua kiểm tra mailbox qua SMTP)
        row_check = QHBoxLayout()
        self.check_email_checkbox = QCheckBox("Kiểm tra địa chỉ email trước khi gửi")
        # Bạn có thể để mặc định là bỏ chọn để tránh kiểm tra mailbox chậm
        self.check_email_checkbox.setChecked(False)
        row_check.addWidget(self.check_email_checkbox)
        main_layout.addLayout(row_check)

        # Row 7: Thanh tiến độ
        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.progress_bar)

        # Row 8: Log
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        main_layout.addWidget(self.log_output)

        # Row 9: Trạng thái
        self.status_label = QLabel("")
        main_layout.addWidget(self.status_label)

        self.main_tab.setLayout(main_layout)
        self.tabs.addTab(self.main_tab, "GỬI MAIL")

        # -------- Tab GENERATE -------- #
        self.generate_tab = QWidget()
        gen_layout = QVBoxLayout()

        row_ai = QHBoxLayout()
        self.ai_server_label = QLabel("Máy chủ AI:")
        row_ai.addWidget(self.ai_server_label)
        self.ai_server_combo = QComboBox()
        # self.ai_server_combo.addItems(list(self.AI_MODELS.keys()))
        self.ai_server_combo.addItems(list(self.AI_MODELS.keys()) + ["LM Studio","Ollama"])
        row_ai.addWidget(self.ai_server_combo)
        self.ai_server_combo.currentIndexChanged.connect(self.update_model_combo)
        gen_layout.addLayout(row_ai)

        row_api = QHBoxLayout()
        self.api_key_label = QLabel("Khoá API:")
        row_api.addWidget(self.api_key_label)
        self.api_key_input = QLineEdit()
        row_api.addWidget(self.api_key_input)
        gen_layout.addLayout(row_api)
        
        self.model_label = QLabel("Mô hình:")  # Nhãn cho combobox model
        gen_layout.addWidget(self.model_label)
        self.model_combo = QComboBox()  # Combobox để chọn model
        gen_layout.addWidget(self.model_combo)
        
       # Trong phần Tab GENERATE
        self.local_ai_url_label = QLabel("Đường dẫn Local AI:")
        gen_layout.addWidget(self.local_ai_url_label)
        self.local_ai_url_input = QLineEdit()
        self.local_ai_url_input.setVisible(False)  # Ẩn ô nhập ban đầu
        gen_layout.addWidget(self.local_ai_url_input)
        # Kết nối sự kiện thay đổi của ai_server_combo
        self.ai_server_combo.currentIndexChanged.connect(self.toggle_local_ai_url_input)

        self.prompt_label = QLabel("Nhập yêu cầu cho AI:")
        gen_layout.addWidget(self.prompt_label)
        self.prompt_input = QTextEdit()
        self.prompt_input.setMinimumHeight(100)
        gen_layout.addWidget(self.prompt_input)

        self.auto_integration_checkbox = QCheckBox("Tự động tích hợp vào mail")
        gen_layout.addWidget(self.auto_integration_checkbox)

        row_buttons = QHBoxLayout()
        self.generate_button = QPushButton("Tạo nội dung")
        self.generate_button.clicked.connect(self.generate_content)
        row_buttons.addWidget(self.generate_button)
        self.apply_button = QPushButton("Áp dụng cho Nội dung mail")
        self.apply_button.clicked.connect(self.apply_generated_content)
        self.apply_button.setEnabled(False)
        row_buttons.addWidget(self.apply_button)
        gen_layout.addLayout(row_buttons)

        self.generated_output = QTextEdit()
        self.generated_output.setReadOnly(True)
        self.generated_output.setMinimumHeight(150)
        gen_layout.addWidget(self.generated_output)

        self.gen_status_label = QLabel("")
        gen_layout.addWidget(self.gen_status_label)

        self.generate_tab.setLayout(gen_layout)
        self.tabs.addTab(self.generate_tab, "TẠO NỘI DUNG TỰ ĐỘNG")
        
        # Tab GATHER MAIL (mới)
        self.setup_gather_tab()

        # -------- Tab ABOUT -------- #
        self.about_tab = QWidget()
        about_layout = QVBoxLayout()
        about_info = {
            "Tác giả": "TekDT",
            "Phần mềm": "AI Bulk Mailer",
            "Phiên bản": version,
            "Ngày phát hành": released_date,
            "Mô tả": "Phần mềm gửi email hàng loạt với khả năng hỗ trợ đa luồng, tạo nội dung tự động bằng nhiều mô hình AI và thu thập tất cả email trên một trang web, hỗ trợ thu thập mail trên nhóm facebook."
        }
        for key, value in about_info.items():
            lbl = QLabel(f"<b>{key}:</b> {value}")
            about_layout.addWidget(lbl)
        about_layout.addStretch()
        self.about_tab.setLayout(about_layout)
        self.tabs.addTab(self.about_tab, "THÔNG TIN")

        # Thiết lập layout chính
        main_container = QVBoxLayout()
        main_container.addWidget(self.tabs)
        self.setLayout(main_container)
        self.setWindowTitle("AI Bulk Mailer")
        self.setGeometry(100, 100, 850, 750)

        self.recipients = []
        self.thread = None
        self.worker = None
        self.gen_thread = None
        self.gen_worker = None
    
    def toggle_oauth_fields(self, state):
        visible = state == Qt.CheckState.Checked.value
        self.client_id_label.setVisible(visible)
        self.client_id_input.setVisible(visible)
        self.client_secret_label.setVisible(visible)
        self.client_secret_input.setVisible(visible)
        self.refresh_token_label.setVisible(visible)
        self.refresh_token_input.setVisible(visible)
    
    def toggle_local_ai_url_input(self):
        if self.ai_server_combo.currentText() == "LM Studio" or self.ai_server_combo.currentText() == "Ollama":
            self.local_ai_url_input.setVisible(True)
            self.local_ai_url_label.setVisible(True)
            if not self.local_ai_url_input.text().strip():
                # Nếu rỗng, tự điền giá trị mặc định
                default_url = self.lm_url_default if self.ai_server_combo.currentText() == "LM Studio" else self.ollama_url_default
                self.local_ai_url_input.setText(default_url)
        else:
            self.local_ai_url_input.setVisible(False)
            self.local_ai_url_label.setVisible(False)
    
    def stop_sending(self):
        if self.is_sending and self.worker:
            self.log_output.append("▶️ Đang yêu cầu dừng luồng...")
            self.worker.stop()
    
    def setup_gather_tab(self):
        """Thiết lập tab Gather Mail."""
        self.gather_tab = QWidget()
        layout = QVBoxLayout()

        # Ô nhập link trang web
        self.url_input = QLineEdit()
        self.url_input.textChanged.connect(self.update_scroll_input_visibility)
        self.url_input.setPlaceholderText("Nhập link trang web hoặc Facebook")
        layout.addWidget(self.url_input)
        
        # Ô nhập XPath
        self.xpath_label = QLabel("XPath (cho nút Xem thêm/Trang tiếp theo):")
        layout.addWidget(self.xpath_label)
        self.xpath_input = QLineEdit()
        self.xpath_input.setPlaceholderText("Ví dụ: //a[contains(text(), 'Xem thêm')]")
        layout.addWidget(self.xpath_input)

        # Trong hàm setup_gather_tab
        self.scroll_times_label = QLabel("Số lần cuộn trang (Facebook):")
        self.scroll_times_input = QLineEdit()
        self.scroll_times_input.setText("50")  # Giá trị mặc định là 50
        self.scroll_times_input.setValidator(QIntValidator(1, 1000))  # Giới hạn giá trị từ 1 đến 1000
        self.scroll_times_label.setVisible(False)  # Ẩn ban đầu
        self.scroll_times_input.setVisible(False)  # Ẩn ban đầu
        layout.addWidget(self.scroll_times_label)
        layout.addWidget(self.scroll_times_input)
        
        # Thêm checkbox "Chạy Chrome ở chế độ ẩn"
        self.headless_checkbox = QCheckBox("Chạy Chrome ở chế độ ẩn (headless mode)")
        layout.addWidget(self.headless_checkbox)

        # Ô tick "Dựa trên SiteMap"
        self.sitemap_checkbox = QCheckBox("Dựa trên SiteMap")
        layout.addWidget(self.sitemap_checkbox)

        # Ô nhập số luồng
        self.thread_count_label = QLabel("Số luồng:")
        layout.addWidget(self.thread_count_label)
        self.thread_count_input = QLineEdit()
        self.thread_count_input.setText("5")  # Giá trị mặc định là 5
        layout.addWidget(self.thread_count_input)

        # Nhãn trạng thái
        self.gather_status_label = QLabel("Trạng thái: Chưa bắt đầu")
        layout.addWidget(self.gather_status_label)
        
        # Nút Thu thập và Nút Stop
        button_layout = QHBoxLayout()
        self.gather_button = QPushButton("Thu thập")
        self.gather_button.clicked.connect(self.gather_emails)
        button_layout.addWidget(self.gather_button)
        self.stop_gathering_button = QPushButton("Dừng")
        self.stop_gathering_button.clicked.connect(self.stop_gathering)
        self.stop_gathering_button.setEnabled(False)  # Ban đầu vô hiệu hóa
        button_layout.addWidget(self.stop_gathering_button)
        layout.addLayout(button_layout)

        # Nút Xuất CSV
        self.export_button = QPushButton("Xuất CSV")
        self.export_button.clicked.connect(self.export_emails_to_csv)
        self.export_button.setEnabled(False)  # Ban đầu vô hiệu hóa
        layout.addWidget(self.export_button)
        
        # Khung Danh sách Email
        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        layout.addWidget(self.output_area)

        self.gather_tab.setLayout(layout)
        self.tabs.addTab(self.gather_tab, "THU THẬP EMAIL")

    def gather_emails(self):
        raw_url = self.url_input.text().strip()
        if not raw_url:
            self.output_area.setText("⚠️ Vui lòng nhập link trang web hoặc Facebook.")
            return

        # Chuẩn hóa URL
        url = self.normalize_url(raw_url)
        if not url:
            self.output_area.setText("⚠️ URL không hợp lệ. Vui lòng kiểm tra lại.")
            return
        
        try:
            max_workers = int(self.thread_count_input.text().strip())
            if max_workers <= 0:
                raise ValueError
        except ValueError:
            self.output_area.setText("⚠️ Số luồng không hợp lệ. Vui lòng nhập số nguyên dương.")
            return

        xpath = self.xpath_input.text().strip()  # Lấy XPath từ ô nhập
        
        # Tự động vô hiệu hóa sitemap nếu là link Facebook
        is_facebook = self.is_facebook_url(url)
        if is_facebook and self.sitemap_checkbox.isChecked():
            self.sitemap_checkbox.setChecked(False)
            self.gather_status_label.setText("⚠️ Sitemap không hỗ trợ cho Facebook, đã bỏ chọn.")
        
        # Đặt cờ bắt đầu thu thập
        self.is_gathering = True

        # Kiểm tra nếu đã có luồng đang chạy
        if hasattr(self, 'thread') and self.thread and self.thread.isRunning():
            self.stop_gathering()

        self.gather_status_label.setText("▶️ Đang thu thập email, vui lòng đợi...")
        self.gather_button.setEnabled(False)
        self.stop_gathering_button.setEnabled(True)
        self.export_button.setEnabled(False)

        self.thread = QThread()
        try:
            scroll_times = int(self.scroll_times_input.text().strip()) if self.is_facebook_url(url) else 0
        except ValueError:
            scroll_times = 50  # Nếu nhập sai, dùng giá trị mặc định 50
        headless = self.headless_checkbox.isChecked()
        self.worker = GatherEmailsWorker(self, url, self.sitemap_checkbox.isChecked(), max_workers, xpath, scroll_times, headless=headless)
        self.worker.moveToThread(self.thread)

        # Kết nối tín hiệu
        self.thread.started.connect(self.worker.run)
        self.worker.status_update.connect(lambda msg: self.gather_status_label.setText(msg))
        self.worker.finished.connect(self.on_gather_finished)
        self.worker.content_signal.connect(self.on_content_gathered)  # Kết nối tín hiệu nội dung
        self.worker.finished.connect(self.cleanup_thread)
        self.worker.update_output.connect(self.update_output_area)

        self.thread.start()
        
    def update_output_area(self, emails, phones):
        output_text = "=== Danh sách Email ===\n"
        output_text += "\n".join(sorted(emails)) if emails else "Chưa có email nào.\n"
        output_text += "\n\n=== Danh sách Số điện thoại ===\n"
        output_text += "\n".join(sorted(phones)) if phones else "Chưa có số điện thoại nào.\n"
        self.output_area.setText(output_text)

    # Hàm kiểm tra và cập nhật trạng thái hiển thị
    def update_scroll_input_visibility(self):
        url = self.url_input.text().strip()
        is_facebook = self.is_facebook_url(url)  # Hàm kiểm tra URL
        self.scroll_times_label.setVisible(is_facebook)
        self.scroll_times_input.setVisible(is_facebook)
    
    def on_content_gathered(self, content):
        """Hiển thị nội dung thu thập được từ Facebook."""
        self.output_area.setText(content if content else "⚠️ Không tìm thấy nội dung.")
        
    def on_gather_finished(self, emails):
        self.extracted_emails = emails
        self.worker.phones  # Lấy tập hợp phones từ worker
        self.update_output_area(self.extracted_emails, self.worker.phones)  # Cập nhật lần cuối
        self.gather_status_label.setText(f"✅ Hoàn tất: Tìm thấy {len(emails)} email và {len(self.worker.phones)} số điện thoại.")
        self.export_button.setEnabled(True)
        self.gather_button.setEnabled(True)
        self.stop_gathering_button.setEnabled(False)
        self.is_gathering = False
        if self.thread:
            self.thread.quit()
            self.thread.wait()
        
    def monitor_futures(self):
        """Theo dõi tiến trình của các luồng và hiển thị kết quả."""
        for future in as_completed(self.futures):
            if not self.is_gathering:  # Nếu bị dừng, thoát vòng lặp
                break
            emails = future.result()
            self.extracted_emails.update(emails)
        if self.is_gathering:  # Nếu không bị dừng, hiển thị kết quả
            self.display_emails()
            self.gather_status_label.setText(f"✅ Hoàn thành! Tìm thấy {len(self.extracted_emails)} email.")
        else:
            self.display_emails()
            self.gather_status_label.setText(f"✅ Hoàn thành! Tìm thấy {len(self.extracted_emails)} email.")
            self.output_area.setText("⛔ Quá trình thu thập đã bị dừng.")
            self.gather_status_label.setText("⛔ Quá trình bị dừng.")
        self.reset_gather_buttons()

    def display_emails(self):
        """Hiển thị danh sách email thu thập được."""
        if self.extracted_emails:
            self.output_area.setText("\n".join(self.extracted_emails))
        else:
            self.output_area.setText("⚠️ Không tìm thấy email nào.")

    def reset_gather_buttons(self):
        """Đặt lại trạng thái các nút sau khi thu thập hoàn thành hoặc bị dừng."""
        self.gather_button.setEnabled(True)
        self.stop_gathering_button.setEnabled(False)
        self.is_gathering = False
        if self.extracted_emails:
            self.export_button.setEnabled(True)  # Cho phép xuất file
    
    def process_url(self, url):
        """Xử lý một URL: tải HTML và trích xuất email."""
        if not self.is_gathering:
            return set()
        html, error = self.fetch_html(url)
        if error:
            return set()
        # emails = set(self.extract_emails_and_phones_from_html(html))
        emails, phones = set(self.main_window.extract_emails_and_phones_from_html(html))
        return emails

    def stop_gathering(self):
        """Dừng tiến trình thu thập email"""
        if hasattr(self, 'worker') and self.worker:
            self.worker.stop()
        
        if hasattr(self, 'thread') and self.thread and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()

        self.gather_status_label.setText("⛔ Quá trình thu thập đã bị dừng.")
        # ✅ Vẫn giữ lại email đã thu thập
        if self.extracted_emails:
            self.output_area.setText("\n".join(self.extracted_emails))  # Hiển thị danh sách email
            self.export_button.setEnabled(True)  # Cho phép xuất CSV
        else:
            self.output_area.setText("⚠️ Không tìm thấy email nào.")
        # Cập nhật UI đúng cách
        self.gather_button.setEnabled(True)
        self.stop_gathering_button.setEnabled(False)

    
    def get_sitemap_url(self, input_url):
        """Lấy URL của sitemap từ bất kỳ liên kết nào của trang web."""
        try:
            parsed_url = urlparse(input_url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"  # Lấy domain gốc

            # Các đường dẫn sitemap phổ biến
            common_sitemap_paths = ["/sitemap.xml", "/sitemap_index.xml"]

            for path in common_sitemap_paths:
                sitemap_url = base_url + path
                response = requests.head(sitemap_url, timeout=5)  # Kiểm tra xem sitemap có tồn tại không
                if response.status_code == 200:
                    self.status_label.setText("✅ Đã tìm thấy sitemap")
                    return sitemap_url
            
            return None  # Không tìm thấy sitemap
        except Exception as e:
            return None

    def normalize_url(self, url):
        """Chuẩn hóa URL: bổ sung giao thức nếu thiếu và trả về dạng hợp lệ."""
        url = url.strip()
        if not url:
            return None
        
        # Bổ sung giao thức nếu thiếu
        if not (url.startswith('http://') or url.startswith('https://')):
            url = 'https://' + url
        
        # Phân tích và chuẩn hóa URL
        try:
            parsed = urlparse(url)
            if not parsed.netloc:  # Nếu không có domain (netloc rỗng)
                return None
            # Tạo lại URL chuẩn với scheme và netloc
            normalized = parsed._replace(scheme='https' if parsed.scheme == '' else parsed.scheme).geturl()
            return normalized
        except Exception:
            return None

    def is_facebook_url(self, url):
        """Kiểm tra xem URL có phải là của Facebook không."""
        return 'facebook.com' in url.lower()
    
    def parse_sitemap(self, sitemap_url):
        """Phân tích sitemap và trả về danh sách các URL, bao gồm sitemap con."""
        urls = []
        try:
            response = requests.get(sitemap_url, timeout=10)
            if response.status_code != 200:
                return []

            content = response.content.decode('utf-8', errors='ignore')
            # Loại bỏ khai báo XML nếu có
            if content.startswith("<?xml"):
                content = re.sub(r'^<\?xml.*?\?>', '', content)
            root = ET.fromstring(content)
            namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

            for elem in root.findall('.//ns:loc', namespace):
                url = elem.text.strip()
                if url.endswith(".xml"):  # Nếu là sitemap con, tiếp tục parse đệ quy
                    urls.extend(self.parse_sitemap(url))
                else:
                    urls.append(url)
            return urls
        except ET.ParseError as e:
            # self.output_area.setText(f"❌ Lỗi khi phân tích sitemap: {e}")
            return []
        except Exception as e:
            # self.output_area.setText(f"❌ Lỗi không xác định khi phân tích sitemap: {e}")
            return []
    
    def fetch_html(self, url):
        """Lấy mã HTML từ URL."""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.content, None
        except requests.exceptions.RequestException as e:
            return None, str(e)
        
    def extract_emails_and_phones_from_html(self, html):
        """
        Trích xuất email và số điện thoại từ mã HTML, hỗ trợ nhiều định dạng từ web và bài đăng Facebook.
        
        Args:
            html (str): Chuỗi HTML cần phân tích.
        
        Returns:
            tuple: (danh sách email, danh sách số điện thoại đã chuẩn hóa).
        """
        soup = BeautifulSoup(html, 'html.parser')
        emails = set()  # Dùng set để tránh trùng lặp
        phones = set()

        # --- Trích xuất Email ---

        # 1. Từ liên kết mailto trong href
        for a in soup.find_all('a', href=True):
            if a['href'].startswith('mailto:'):
                parsed = urlparse(a['href'])
                email = parsed.path  # Lấy phần sau 'mailto:'
                # Kiểm tra định dạng email hợp lệ
                if re.fullmatch(r'(?<!\S)[A-Za-z0-9]+(?:[._%+-][A-Za-z0-9]+)*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?!\S)', email):
                    emails.add(email)

        # 2. Từ văn bản thông thường
        text = soup.get_text(separator=" ")
        email_pattern = r'(?<!\S)[A-Za-z0-9]+(?:[._%+-][A-Za-z0-9]+)*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?!\S)'
        found_emails = re.findall(email_pattern, text)
        emails.update(found_emails)
        print(found_emails)

        # --- Trích xuất Số điện thoại ---

        # Tìm số điện thoại với các định dạng khác nhau
        phone_pattern = r'(?<!\d)(?:\+84|84|0)(?:[\s.-]*\d){9,10}(?!\d)'
        found_phones_raw = re.findall(phone_pattern, text)
        print(found_phones_raw)

        # Chuẩn hóa số điện thoại
        for phone in found_phones_raw:
            # Loại bỏ ký tự không phải số
            cleaned_phone = re.sub(r'\D', '', phone)
            # Chuẩn hóa: thay thế +84 hoặc 84 bằng 0
            if cleaned_phone.startswith('84'):
                standardized_phone = '0' + cleaned_phone[2:]
            elif cleaned_phone.startswith('+84'):
                standardized_phone = '0' + cleaned_phone[3:]
            else:
                standardized_phone = cleaned_phone
            # Kiểm tra độ dài hợp lệ (10 chữ số cho số nội địa Việt Nam)
            if len(standardized_phone) == 10 and standardized_phone.startswith('0'):
                phones.add(standardized_phone)

        return list(emails), list(phones)
    
    def export_emails_to_csv(self):
        """Xuất danh sách email ra file CSV."""
        if not self.extracted_emails:
            self.output_area.setText("⚠️ Không có email nào để xuất.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Lưu danh sách email", "", "CSV Files (*.csv)")
        if file_path:
            try:
                with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    for email in self.extracted_emails:
                        writer.writerow([email])  # Mỗi email một dòng
                self.output_area.setText(f"✅ Xuất thành công {len(self.extracted_emails)} email vào {file_path}.")
            except Exception as e:
                self.output_area.setText(f"❌ Lỗi khi xuất file: {e}")

    # Hàm cập nhật danh sách model
    def update_model_combo(self):
        ai_server = self.ai_server_combo.currentText()  # Lấy AI được chọn
        if ai_server == "LM Studio" or ai_server == "Ollama" :
            # Sử dụng self.local_ai_url làm giá trị cơ sở
            local_ai_url = self.local_ai_url
            # Nếu người dùng đã nhập URL mới trong local_ai_url_input, ưu tiên giá trị đó
            input_url = self.local_ai_url_input.text().strip()
            if input_url:
                local_ai_url = input_url
            
            try:
                # Gửi yêu cầu đến API /v1/models
                response = requests.get(f"{local_ai_url}/v1/models")
                if response.status_code == 200:
                    models = response.json().get("data", [])  # Lấy danh sách mô hình
                    if models:
                        # Điền danh sách mô hình vào model_combo
                        model_names = [model["id"] for model in models]
                        self.model_combo.clear()
                        self.model_combo.addItems(model_names)
                    else:
                        # Thông báo nếu không có mô hình
                        QMessageBox.warning(self, "Không có mô hình", 
                                            "Không có mô hình nào được tải trong {ai_server}. Vui lòng tải mô hình.")
                else:
                    # Thông báo nếu không kết nối được
                    QMessageBox.warning(self, "Lỗi kết nối", 
                                        f"Không thể kết nối đến {ai_server}: {response.status_code}")
            except requests.exceptions.RequestException as e:
                # Thông báo nếu không ping được localhost hoặc URL
                QMessageBox.warning(self, "Lỗi kết nối", 
                                    f"Không thể kết nối đến {ai_server}. Vui lòng bật kết nối trong {ai_server}: {e}")
            except ValueError:
                # Thông báo nếu phản hồi không phải JSON hợp lệ
                QMessageBox.warning(self, "Lỗi định dạng", 
                                    "Phản hồi từ {ai_server} không phải là JSON hợp lệ.")
        else:
            # Xử lý cho các máy chủ AI khác
            models = self.AI_MODELS.get(ai_server, [])  # Lấy danh sách model tương ứng
            self.model_combo.clear()  # Xóa danh sách model cũ
            self.model_combo.addItems(models)  # Thêm danh sách model mới
            pass

    def update_smtp_provider(self):
        """Tự động chọn SMTP dựa trên tên miền email."""
        email = self.email_input.text().strip()
        if '@' in email:
            domain = email.split('@')[1].lower()
            for provider, config in self.SMTP_CONFIG.items():
                if domain in config['server']:
                    self.provider_combo.setCurrentText(provider)
                    return
            self.provider_combo.setCurrentText("Khác")
        else:
            self.provider_combo.setCurrentText("Khác")

    def tab_changed(self, index):
        try:
            if index == 1:  # Chuyển sang RAW HTML
                html_content = self.rich_editor.toHtml()
                self.raw_editor.setPlainText(html_content)
            elif index == 0:  # Chuyển sang Soạn thảo trực quan
                html_content = self.raw_editor.toPlainText()
                self.rich_editor.setHtml(html_content)
        except Exception as e:
            self.status_label.setText(f"❌ Lỗi khi chuyển đổi tab: {e}")

    def provider_changed(self, index):
        provider = self.provider_combo.currentText()
        if provider == "Khác":
            self.custom_smtp_label.setVisible(True)
            self.custom_smtp_input.setVisible(True)
            self.custom_port_label.setVisible(True)
            self.custom_port_input.setVisible(True)
        else:
            self.custom_smtp_label.setVisible(False)
            self.custom_smtp_input.setVisible(False)
            self.custom_port_label.setVisible(False)
            self.custom_port_input.setVisible(False)

    def load_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Mở tập tin CSV", "", "CSV Files (*.csv)")
        if file_path:
            try:
                with open(file_path, newline='', encoding='utf-8') as csvfile:
                    reader = csv.reader(csvfile)
                    self.recipients = [row[0] for row in reader if row]
                    self.status_label.setText(f"✅ Đã tải {len(self.recipients)} người nhận.")
                    self.log_output.append(f"✅ Đã tải {len(self.recipients)} người nhận từ tập tin.")
            except Exception as e:
                self.status_label.setText(f"❌ Lỗi khi tải tập tin: {e}")
                self.log_output.append(f"❌ Lỗi khi tải tập tin: {e}")
    
    def verify_email_address(self, email, from_address="test@example.com", timeout=10, check_mailbox=True):
        # 1. Kiểm tra cú pháp email
        pattern = r"(?<!\S)[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?!\S)"
        if not re.fullmatch(pattern, email):
            return False, "❌ Định dạng email không hợp lệ."
        
        # Nếu không tick kiểm tra đầy đủ, chỉ dựa vào cú pháp
        if not check_mailbox:
            return True, "❌ Email hợp lệ (không kiểm tra tên miền/hộp thư)."
        
        # 2. Kiểm tra sự tồn tại của tên miền (MX hoặc A record)
        try:
            domain = email.split('@')[1]
            try:
                # Ưu tiên kiểm tra MX record
                answers = dns.resolver.resolve(domain, 'MX', lifetime=timeout)
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                # Nếu không có MX, thử A record
                answers = dns.resolver.resolve(domain, 'A', lifetime=timeout)
        except Exception as e:
            return False, f"❌ Tên miền không hợp lệ hoặc không tồn tại: {e}"
        
        # 3. Kiểm tra hộp thư qua SMTP
        try:
            # Lấy MX record đầu tiên nếu có, nếu không sử dụng domain trực tiếp
            mx_record = answers[0].exchange.to_text() if hasattr(answers[0], 'exchange') else domain
            server = smtplib.SMTP(timeout=timeout)
            server.connect(mx_record)
            server.helo(server.local_hostname)
            server.mail(from_address)
            code, _ = server.rcpt(email)
            server.quit()
            if code != 250:
                return False, "❌ Hộp thư không tồn tại hoặc bị từ chối bởi server."
        except Exception as e:
            return False, f"❌ Kiểm tra mailbox không thành công: {e}"
        
        return True, "✅ Email hợp lệ."

    def send_emails(self):
        self.recipients_sent = []  # Đặt lại danh sách email đã gửi trước đó
        # Kiểm tra xem có đang gửi email không
        if self.is_sending and self.thread and self.thread.isRunning():
            self.status_label.setText("♾️ Đang thực hiện gửi email. Vui lòng đợi.")
            self.worker.stop()  # Gọi phương thức stop của worker
            self.thread.quit()  # Thoát luồng
            self.thread.wait()  # Đợi luồng dừng hoàn toàn
            self.is_sending = False
            self.stop_sending()
            self.status_label.setText("❌ Đã dừng luồng gửi email trước đó.")
            pass
            return
        
        # Vô hiệu hóa nút "Send Emails"
        self.send_button.setEnabled(False)
        self.stop_sending_button.setEnabled(True)
        QApplication.processEvents()
        self.status_label.setText("♾️ Đang gửi email...")
        self.is_sending = True  # Đặt trạng thái đang gửi
        
        sender_email = self.email_input.text().strip()
        password = self.password_input.text().strip()
        subject = self.subject_input.text().strip()
        reply_to = self.reply_input.text().strip()
        cc = self.cc_input.text().strip()
        bcc = self.bcc_input.text().strip()

        if self.tab_widget.currentIndex() == 1:
            self.rich_editor.setHtml(self.raw_editor.toPlainText())
        body = self.rich_editor.toHtml()

        provider = self.provider_combo.currentText()
        connection_security = self.security_combo.currentText()
        if provider == "Khác":
            smtp_server = self.custom_smtp_input.text().strip()
            try:
                port = int(self.custom_port_input.text().strip())
            except ValueError:
                self.status_label.setText("❌ Sai cổng.")
                self.log_output.append("❌ Cổng được nhập không đúng.")
                return
            if not smtp_server:
                self.status_label.setText("⚠️ Vui lòng nhập máy chủ SMTP hợp lệ.")
                self.log_output.append("❌ Máy chủ SMTP bị thiếu.")
                return
        else:
            config = self.SMTP_CONFIG.get(provider)
            smtp_server = config['server']
            # Chọn cổng dựa trên kiểu bảo mật
            if connection_security == "SSL":
                port = config.get("port_ssl", config.get("port"))
            elif connection_security == "TLS":
                port = config.get("port_tls", config.get("port"))
            else:  # Nếu "None"
                port = config.get("port", config.get("port_tls", config.get("port_ssl")))

        if not self.recipients:
            self.status_label.setText("⚠️ Danh sách người nhận trống.")
            self.log_output.append("⚠ ️Danh sách người nhận trống.")
            return
        
        # Xử lý OAuth2
        use_oauth = self.oauth_checkbox.isChecked()
        oauth_config = None
        refresh_token = None
        if use_oauth:
            provider_lower = provider.lower()
            if provider_lower in ["gmail", "hotmail/outlook"]:
                oauth_config = OAUTH_CONFIG.get(provider, {})
                oauth_config["provider"] = provider_lower
                oauth_config["client_id"] = self.client_id_input.text().strip()
                oauth_config["client_secret"] = self.client_secret_input.text().strip()
                refresh_token = self.refresh_token_input.text().strip()
                if not all([oauth_config["client_id"], oauth_config["client_secret"], refresh_token]):
                    self.status_label.setText("⚠️ Vui lòng nhập đầy đủ Client ID, Client Secret và Refresh Token.")
                    self.send_button.setEnabled(True)
                    self.is_sending = False
                    return
        
        # --- Kiểm tra email trước khi gửi ---
        invalid_emails = []
        valid_recipients = []
        # Lấy trạng thái của checkbox: nếu tick => kiểm tra đầy đủ (cả mailbox), nếu không => bỏ qua mailbox
        check_mailbox = self.check_email_checkbox.isChecked()
        for recipient in self.recipients:
            # is_valid, message = self.verify_email_address(recipient, self.email_input.text().strip(), check_mailbox)
            is_valid, message = self.verify_email_address(recipient, from_address=self.email_input.text().strip(), check_mailbox=check_mailbox)
            if is_valid:
                valid_recipients.append(recipient)
            else:
                invalid_emails.append(f"{recipient}: {message}")
        
        if invalid_emails:
            self.log_output.append("⚠️ Một số email không hợp lệ:")
            for err in invalid_emails:
                self.log_output.append(err)
        
        if not valid_recipients:
            self.status_label.setText("⚠️ Không có email hợp lệ để gửi.")
            self.send_button.setEnabled(True)
            self.is_sending = False
            return
        
        # Cập nhật danh sách người nhận chỉ chứa email hợp lệ
        self.recipients = valid_recipients
        # --- Kết thúc kiểm tra ---
            
        # Lấy các thông số AI từ giao diện để tạo nội dung độc đáo cho mỗi email
        auto_integration = self.auto_integration_checkbox.isChecked()
        ai_server = self.ai_server_combo.currentText()
        api_key = self.api_key_input.text().strip()
        ai_prompt = self.prompt_input.toPlainText().strip()
        model = self.model_combo.currentText()
        local_ai_url = self.local_ai_url_input.text().strip()
        # Lấy và kiểm tra giá trị min_delay và max_delay từ giao diện
        try:
            min_delay = int(self.min_delay_input.text().strip())
            max_delay = int(self.max_delay_input.text().strip())
            if min_delay < 0 or max_delay < 0 or min_delay > max_delay:
                raise ValueError("Giá trị không hợp lệ")
        except ValueError:
            self.status_label.setText("⚠️ Vui lòng nhập giá trị hợp lệ cho thời gian chờ.")
            self.send_button.setEnabled(True)
            self.is_sending = False
            return
        
        self.progress_bar.setRange(0, len(self.recipients))
        self.progress_bar.setValue(0)
        self.log_output.clear()
        self.status_label.setText("♾️ Đang gửi mail...")
        # Lưu tổng số mail ban đầu
        self.total_recipients = len(self.recipients)

        self.thread = QThread()
        self.worker = EmailSenderWorker(self, smtp_server, port, sender_email, password, subject, body, self.recipients, connection_security, reply_to, cc=cc, bcc=bcc, use_oauth=use_oauth, oauth_config=oauth_config, refresh_token=refresh_token, auto_integration=auto_integration, ai_server=ai_server, api_key=api_key, ai_prompt=ai_prompt, model=model, min_delay=min_delay, max_delay=max_delay, local_ai_url=local_ai_url)
        self.worker.success_signal.connect(self.on_email_sent_successfully)
        self.worker.moveToThread(self.thread)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.log_signal.connect(lambda msg: self.log_output.append(msg))
        self.worker.summary_signal.connect(self.on_summary)
        self.worker.error_signal.connect(self.on_error)
        self.thread.started.connect(self.worker.run)
        
        # self.worker.summary_signal.connect(self.thread.quit)
        # self.worker.summary_signal.connect(self.worker.deleteLater)
        # self.thread.finished.connect(self.thread.deleteLater)
        # self.thread.finished.connect(lambda: self.stop_sending_button.setEnabled(False))
        # self.thread.finished.connect(lambda: self.send_button.setEnabled(True))
        # self.thread.finished.connect(lambda: setattr(self, 'is_sending', False))  # Reset flag khi luồng hoàn thành
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.on_sending_finished) # Tạo hàm mới để xử lý UI

        self.thread.start()
        QApplication.processEvents()

    def on_email_sent_successfully(self, email):
        if email in self.recipients:
            self.recipients.remove(email)  # Xóa email khỏi danh sách
            self.recipients_sent.append(email)  # Thêm email vào danh sách đã gửi
            
        current_sent = len(self.recipients_sent)
        total = len(self.recipients)
        self.status_label.setText(f"✅ Đã gửi đến {email} ({current_sent}/{self.total_recipients})")
        self.save_settings()           # Lưu ngay vào settings.json
        # Cập nhật thanh tiến trình
        self.progress_bar.setValue(current_sent)
    
    def on_error(self, error_msg):
        self.status_label.setText(f"❌ Lỗi: {error_msg}")
        self.log_output.append(f"❌ Lỗi: {error_msg}")
        # Chỉ cần dừng luồng, không cần wait()
        if self.thread and self.thread.isRunning():
            self.worker.stop() # Yêu cầu worker dừng lại sớm
            self.thread.quit()

    def on_summary(self, summary):
        total = summary["total"]
        success = summary["success"]
        failed = summary["failed"]
        failed_recipients = summary["failed_recipients"]
        status_msg = f"✅ Đã hoàn thành: {success}/{total} email được gửi thành công, {failed} thất bại"
        self.status_label.setText(status_msg)
        self.log_output.append("\n=== Tổng kết Mail Gửi ===")
        self.log_output.append(status_msg)
        if failed_recipients:
            self.log_output.append("❌ Danh sách gửi không thành công:")
            for recipient, error in failed_recipients.items():
                self.log_output.append(f"- {recipient}: {error}")
        if self.thread and self.thread.isRunning():
            self.thread.quit()

    def on_sending_finished(self):
        """Được gọi khi luồng gửi mail kết thúc."""
        self.is_sending = False
        self.send_button.setEnabled(True)
        self.stop_sending_button.setEnabled(False)
        self.thread = None # Đánh dấu luồng đã được dọn dẹp
        self.worker = None
        self.log_output.append("------------------\nLuồng gửi mail đã kết thúc.")
    
    def generate_content(self):
        # Kiểm tra nếu có thread cũ, đảm bảo nó đã kết thúc hoàn toàn trước khi tạo mới
        if hasattr(self, 'gen_thread') and self.gen_thread is not None:
            if self.gen_thread.isRunning():
                self.gen_thread.quit()
                self.gen_thread.wait()
            self.gen_thread.deleteLater()  # Xóa QThread cũ
            self.gen_thread = None  # Đặt lại thành None
            
        ai_server = self.ai_server_combo.currentText()
        api_key = self.api_key_input.text().strip()
        prompt = self.prompt_input.toPlainText().strip()
        model = self.model_combo.currentText()
        if not prompt:
            self.gen_status_label.setText("⚠️ Vui lòng nhập prompt.")
            return
        if not model:
            self.gen_status_label.setText("⚠️ Vui lòng chọn model.")
            return
            
        # Lấy local_ai_url TẠI ĐÂY, trên luồng chính
        local_ai_url = self.local_ai_url_input.text().strip()

        self.gen_status_label.setText("♾️ Đang tạo nội dung...")
        self.generate_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        # Tạo luồng mới
        self.gen_thread = QThread()
        self.gen_worker = ContentGeneratorWorker(ai_server, api_key, prompt, model, local_ai_url) 
        self.gen_worker.moveToThread(self.gen_thread)
        # Kết nối tín hiệu
        self.gen_worker.result_signal.connect(self.on_gen_result)
        self.gen_worker.error_signal.connect(self.on_gen_error)
        self.gen_thread.started.connect(self.gen_worker.run)
        # Đảm bảo dừng thread sau khi hoàn thành
        self.gen_worker.result_signal.connect(self.cleanup_thread)
        self.gen_worker.error_signal.connect(self.cleanup_thread)
        self.gen_thread.start()

    def cleanup_thread(self):
        if hasattr(self, 'worker') and self.worker is not None:
            self.worker.deleteLater()
            self.worker = None
        if hasattr(self, 'thread') and self.thread is not None:
            self.thread.quit()
            self.thread.wait()
            self.thread.deleteLater()
            self.thread = None
        self.gather_button.setEnabled(True)
    
    def on_gen_result(self, result):
        self.generated_output.setPlainText(result)
        self.gen_status_label.setText("✅ Tạo nội dung thành công!")
        self.generate_button.setEnabled(True)
        self.apply_button.setEnabled(True)
        
        # **Điều kiện: Yêu cầu người dùng xác nhận**
        reply = QMessageBox.question(self, 'Xác nhận nội dung',
                             'Bạn có muốn áp dụng nội dung này cho email không?',
                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                             QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.apply_generated_content()  # Áp dụng nội dung nếu được xác nhận
        else:
            self.gen_status_label.setText("⚠️ Nội dung không được áp dụng.")

    def on_gen_error(self, error_msg):
        self.gen_status_label.setText(f"❌ Lỗi: {error_msg}")
        self.generate_button.setEnabled(True)

    def apply_generated_content(self):
        generated = self.generated_output.toPlainText()
        if generated:
            self.rich_editor.setHtml(generated)
            if self.tab_widget.currentIndex() == 1:
                self.raw_editor.setPlainText(generated)
            self.status_label.setText("✅ Nội dung được tạo đã áp dụng cho Nội dung email.")

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                    
                # Tải SMTP_CONFIG
                self.SMTP_CONFIG = settings.get("SMTP_CONFIG", DEFAULT_SETTINGS["SMTP_CONFIG"])
                self.AI_MODELS = settings.get("AI_MODELS", DEFAULT_SETTINGS["AI_MODELS"])
                self.lm_url_default = settings.get("lm_url_default", DEFAULT_SETTINGS["lm_url_default"])
                self.ollama_url_default = settings.get("ollama_url_default", DEFAULT_SETTINGS["ollama_url_default"])
                # Nếu có key nào chưa tồn tại, cập nhật settings để lưu sau
                update_needed = False
                if "SMTP_CONFIG" not in settings:
                    settings["SMTP_CONFIG"] = self.SMTP_CONFIG
                    update_needed = True
                if "AI_MODELS" not in settings:
                    settings["AI_MODELS"] = self.AI_MODELS
                    update_needed = True
                if "lm_url_default" not in settings:
                    settings["lm_url_default"] = "http://localhost:1234"
                    update_needed = True
                if "ollama_url_default" not in settings:
                    settings["ollama_url_default"] = "http://localhost:11434"
                    update_needed = True
                # Lưu lại file nếu có thay đổi
                if update_needed:
                    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                        json.dump(settings, f, ensure_ascii=False, indent=4)
   
                if "local_ai_url" in settings:
                    self.local_ai_url = settings["local_ai_url"]
                self.email_input.setText(settings.get("email", ""))
                self.password_input.setText(settings.get("password", ""))
                self.subject_input.setText(settings.get("subject", ""))
                self.reply_input.setText(settings.get("reply_to", ""))
                self.cc_input.setText(settings.get("cc_input", ""))
                self.bcc_input.setText(settings.get("bcc_input", ""))
                # self.provider_combo.setCurrentIndex(settings.get("smtp_provider_index", 0))
                self.provider_combo.setCurrentText(settings.get("smtp_provider", ""))
                self.custom_smtp_input.setText(settings.get("custom_smtp", ""))
                self.custom_port_input.setText(str(settings.get("custom_port", "")))
                self.rich_editor.setHtml(settings.get("email_body", ""))
                self.raw_editor.setPlainText(settings.get("email_body", ""))
                self.api_key_input.setText(settings.get("api_key", ""))
                self.prompt_input.setPlainText(settings.get("prompt", ""))
                self.min_delay_input.setText(settings.get("min_delay", ""))
                self.max_delay_input.setText(settings.get("max_delay", ""))
                self.generated_output.setPlainText(settings.get("generated_content", ""))
                self.auto_integration_checkbox.setChecked(settings.get("auto_integration", False))
                self.recipients = settings.get("recipients", [])
                if self.recipients:
                    self.status_label.setText(f"✅ Đã tải {len(self.recipients)} người nhận từ tập tin lưu trữ.")
                self.security_combo.setCurrentText(settings.get("connection_security", "SSL"))
                self.check_email_checkbox.setChecked(settings.get("check_email", False))
                self.url_input.setText(settings.get("gather_url", ""))
                self.xpath_input.setText(settings.get("xpath", ""))
                self.sitemap_checkbox.setChecked(settings.get("sitemap", False))
                self.headless_checkbox.setChecked(settings.get("headless_mode", False))
                self.thread_count_input.setText(settings.get("thread_count", "5"))
                # Load settings từ file hoặc cấu hình
                ai_server = settings.get("ai_server", "ChatGPT")
                model = settings.get("model", "")
                self.update_model_combo()  # Cập nhật danh sách model
                self.ai_server_combo.setCurrentText(settings.get("ai_server", ""))
                self.AI_MODELS = settings.get("AI_MODELS", self.AI_MODELS)
                if model in self.AI_MODELS.get(ai_server, []):
                    self.model_combo.setCurrentText(model)  # Đặt model đã lưu
                if ai_server == "LM Studio":
                    self.local_ai_url = settings.get("local_ai_url") or settings.get("lm_url_default", "http://localhost:1234")
                elif ai_server == "Ollama":
                    self.local_ai_url = settings.get("local_ai_url") or settings.get("ollama_url_default", "http://localhost:11434")
                self.local_ai_url_input.setText(self.local_ai_url)
                self.toggle_local_ai_url_input()  # Gọi để cập nhật trạng thái hiển thị
                self.oauth_checkbox.setChecked(settings.get("use_oauth", False))
                self.client_id_input.setText(settings.get("client_id", ""))
                self.client_secret_input.setText(settings.get("client_secret", ""))
                self.refresh_token_input.setText(settings.get("refresh_token", ""))
                self.toggle_oauth_fields(Qt.CheckState.Checked.value if settings.get("use_oauth", False) else Qt.CheckState.Unchecked.value)
            except Exception as e:
                if hasattr(self, 'status_label'):
                    self.status_label.setText(f"❌ Lỗi khi tải các thiết lập: {e}")
                    print(f"❌ Lỗi khi tải các thiết lập: {e}")
                    # Nếu lỗi, sử dụng giá trị mặc định
                    self.local_ai_url = "http://localhost:1234"
                    self.SMTP_CONFIG = DEFAULT_SETTINGS["SMTP_CONFIG"]
                    self.AI_MODELS = DEFAULT_SETTINGS["AI_MODELS"]
        else:
            # Nếu file không tồn tại, dùng giá trị mặc định và tạo file mới
            self.local_ai_url = "http://localhost:1234"
            self.SMTP_CONFIG = DEFAULT_SETTINGS["SMTP_CONFIG"]
            self.AI_MODELS = DEFAULT_SETTINGS["AI_MODELS"]
            settings = {
                "SMTP_CONFIG": self.SMTP_CONFIG,
                "AI_MODELS": self.AI_MODELS,
                "lm_url_default": "http://localhost:1234",
                "ollama_url_default": "http://localhost:11434"
            }
            try:
                with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(settings, f, ensure_ascii=False, indent=4)
            except Exception as e:
                print(f"❌ Lỗi khi tạo file settings: {e}")
                    
    def save_settings(self):
        if self.tab_widget.currentIndex() == 1:
            self.rich_editor.setHtml(self.raw_editor.toPlainText())
        # Đọc dữ liệu hiện tại từ file settings.json để không ghi đè mất cookie
        current_settings = {}
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    current_settings = json.load(f)
            except Exception as e:
                print(f"❌ Lỗi khi đọc file settings hiện tại: {e}")
        settings = {
            "SMTP_CONFIG": self.SMTP_CONFIG,
            "AI_MODELS": self.AI_MODELS,
            "email": self.email_input.text(),
            "password": self.password_input.text(),
            "subject": self.subject_input.text(),
            "reply_to": self.reply_input.text(),
            "cc_input": self.cc_input.text(),
            "bcc_input": self.bcc_input.text(),
            "smtp_provider": self.provider_combo.currentText(),
            "custom_smtp": self.custom_smtp_input.text(),
            "custom_port": self.custom_port_input.text(),
            "email_body": self.rich_editor.toHtml(),
            "ai_server_index": self.ai_server_combo.currentIndex(),
            "api_key": self.api_key_input.text(),
            "prompt": self.prompt_input.toPlainText(),
            "generated_content": self.generated_output.toPlainText(),
            "auto_integration": self.auto_integration_checkbox.isChecked(),
            "recipients": self.recipients,
            "ai_server": self.ai_server_combo.currentText(),
            "model": self.model_combo.currentText(),
            "local_ai_url": self.local_ai_url_input.text(),
            "connection_security": self.security_combo.currentText(),
            "check_email": self.check_email_checkbox.isChecked(),
            "gather_url": self.url_input.text(),
            "xpath": self.xpath_input.text(),
            "sitemap": self.sitemap_checkbox.isChecked(),
            "headless_mode": self.headless_checkbox.isChecked(),
            "thread_count": self.thread_count_input.text(),
            "use_oauth": self.oauth_checkbox.isChecked(),
            "client_id": self.client_id_input.text(),
            "client_secret": self.client_secret_input.text(),
            "refresh_token": self.refresh_token_input.text(),
            "min_delay": self.min_delay_input.text(),
            "max_delay": self.max_delay_input.text(),
        }
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.status_label.setText(f"❌ Lỗi khi lưu các thiết lập: {e}")

    def delayed_save_settings(self):
        if hasattr(self, "_save_timer"):
            self._save_timer.stop()  # Hủy timer trước đó nếu có
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)  # Chỉ chạy một lần
        self._save_timer.timeout.connect(self.save_settings)
        self._save_timer.start(500)  # Đợi 500ms trước khi lưu
    
    def closeEvent(self, event):
        self.save_settings()
        # if self.thread and self.thread.isRunning():
        try:
            if hasattr(self, 'thread') and self.thread is not None:
                if self.thread.isRunning():
                    self.thread.quit()
                    self.thread.wait()
                    self.thread.deleteLater()
                    self.thread = None
            # if self.gen_thread and self.gen_thread.isRunning():
            if hasattr(self, 'gen_thread') and self.gen_thread is not None:
                if self.gen_thread.isRunning():
                    self.gen_thread.quit()
                    self.gen_thread.wait()
                    self.gen_thread.deleteLater()
                    self.gen_thread = None
            event.accept()
        except RuntimeError:
            pass

class GatherEmailsWorker(QObject):
    finished = pyqtSignal(set)  # Tín hiệu hoàn tất thu thập
    content_signal = pyqtSignal(str)  # Tín hiệu trả về nội dung văn bản từ Facebook
    status_update = pyqtSignal(str)  # Tín hiệu cập nhật trạng thái
    update_output = pyqtSignal(set, set)

    def __init__(self, main_window, url, use_sitemap, max_workers, xpath, scroll_times=50, headless=False):
        super().__init__()
        self.main_window = main_window  # Truy cập hàm từ BulkEmailSender
        self.url = url
        self.use_sitemap = use_sitemap
        self.max_workers = max_workers
        self.xpath = xpath
        self.is_running = True
        self.emails = set()
        self.phones = set()
        self.content = ""
        self.session = None
        self.driver = None
        self.scroll_times = scroll_times
        self.headless = headless
        
    def convert_to_mbasic(self, url):
        """Chuyển URL Facebook sang phiên bản mbasic."""
        if self.main_window.is_facebook_url(url):  # Gọi từ main_window
            parsed_url = urlparse(url)
            return f"https://m.facebook.com{parsed_url.path}{parsed_url.query}"
        return url
    
    def setup_selenium_driver(self):
        """Cấu hình Selenium với Chrome, tắt JavaScript và tối ưu hóa."""
        chrome_options = Options()
        
        # Kích hoạt headless mode nếu được chọn
        if self.headless:
            chrome_options.add_argument('--headless')
        
        # Tắt JavaScript
        chrome_options.add_argument('--disable-javascript')
        
        # Tắt hình ảnh để tăng tốc độ
        prefs = {
            "profile.managed_default_content_settings.images": 2,  # 2 = tắt hình ảnh
            "profile.managed_default_content_settings.stylesheets": 2,  # Tắt CSS nếu cần
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        # Giả lập User-Agent đơn giản cho mbasic
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Mobile Safari/537.36')
        
        driver = webdriver.Chrome(options=chrome_options)
        return driver
            
    def is_logged_in(self):
        if not hasattr(self, 'driver') or self.driver is None:
            print("Driver chưa được khởi tạo trong is_logged_in.")
            self.status_update.emit("❌ Driver chưa được khởi tạo trong is_logged_in.")
            return False
        try:
            print("Đang kiểm tra trạng thái đăng nhập...")
            self.driver.get('https://m.facebook.com/login.php')
            WebDriverWait(self.driver, 10).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            try:
                self.driver.find_element(By.XPATH, "//div[@role='tablist' and @data-type='container' and @data-mcomponent='MContainer' and contains(@class, 'm') and @data-actual-height]")
                print("Không tìm thấy form đăng nhập, đã đăng nhập.")
                self.status_update.emit("✅ Không tìm thấy form đăng nhập, đã đăng nhập.")
                return True
            except NoSuchElementException:
                print("Tìm thấy form đăng nhập, chưa đăng nhập.")
                self.status_update.emit("⚠️ Tìm thấy form đăng nhập, chưa đăng nhập.")
                return False
        except Exception as e:
            print(f"Lỗi trong is_logged_in: {e}")
            self.status_update.emit(f"❌ Lỗi khi kiểm tra đăng nhập: {e}")
            return False
            
    def load_cookies(self):
        cookie_file = 'facebook_cookies.pkl'
        if os.path.exists(cookie_file):
            try:
                with open(cookie_file, 'rb') as file:
                    cookies = pickle.load(file)
                if self.driver is None:
                    self.driver = self.setup_selenium_driver()
                self.driver.get('https://m.facebook.com/login.php')
                for cookie in cookies:
                    self.driver.add_cookie(cookie)
                self.driver.refresh()
                WebDriverWait(self.driver, 10).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )
                self.status_update.emit("✅ Đã nạp cookie từ file facebook_cookies.pkl!")
                # Kiểm tra trạng thái driver
                try:
                    current_url = self.driver.current_url
                    print(f"Driver vẫn hoạt động sau khi nạp cookie. URL hiện tại: {current_url}")
                except Exception as e:
                    print(f"Driver đã bị đóng sau khi nạp cookie: {e}")
                    self.status_update.emit(f"❌ Driver đã bị đóng sau khi nạp cookie: {e}")
                    return False
                return True
            except Exception as e:
                self.status_update.emit(f"❌ Lỗi khi nạp cookie từ file: {e}")
                print(f"Lỗi khi nạp cookie: {e}")
                return False
        else:
            self.status_update.emit("⚠️ Không tìm thấy file facebook_cookies.pkl.")
            return False
        
    def save_cookies(self, cookies):
        """Lưu cookie vào file facebook_cookies.pkl."""
        try:
            with open('facebook_cookies.pkl', 'wb') as file:
                pickle.dump(cookies, file)
            self.status_update.emit("✅ Đã lưu cookie vào file facebook_cookies.pkl!")
        except Exception as e:
            self.status_update.emit(f"❌ Lỗi khi lưu cookie vào file: {e}")
    
    def check_facebook_login(self):
        """
        Kiểm tra xem đã đăng nhập vào Facebook thành công chưa bằng cách chọn ngẫu nhiên một phương pháp kiểm tra.
        """
        methods = [
            lambda: self.driver.refresh(),  # 1. Làm mới trang
            lambda: self.driver.execute_script("window.scrollBy(0, 200); time.sleep(1); window.scrollBy(0, -200);"),  # 2. Cuộn trang
            lambda: self.driver.execute_script("location.reload(true);"),  # 3. Buộc tải lại trang bằng JavaScript
            lambda: WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'logout')]"))),  # 4. Kiểm tra phần tử đăng xuất
            lambda: self.driver.find_element(By.XPATH, "//a[@href='https://m.facebook.com/']").click() if self.driver.find_elements(By.XPATH, "//a[@href='https://m.facebook.com/']") else None,  # 5. Nhấn vào logo
            lambda: self.driver.execute_script("sessionStorage.clear(); localStorage.clear(); location.reload();"),  # 6. Xóa sessionStorage & localStorage
        ]

        # Chọn ngẫu nhiên một phương pháp kiểm tra
        method = random.choice(methods)
        
        try:
            print(f"🔄 Đang kiểm tra trạng thái đăng nhập bằng phương pháp: {method.__name__}")
            result = method()
            time.sleep(2)  # Chờ một chút để trang cập nhật
            
            # Kiểm tra trạng thái đăng nhập theo phương pháp 7
            if isinstance(result, bool):
                return result
            
            return True  # Nếu không gặp lỗi, giả định là đã đăng nhập
        except Exception as e:
            print(f"⚠️ Lỗi khi kiểm tra đăng nhập: {e}")
            return False
    
    def login_facebook_selenium(self):
        if not hasattr(self, 'driver') or self.driver is None:
            self.driver = self.setup_selenium_driver()

        if self.load_cookies():
            try:
                current_url = self.driver.current_url
                print(f"Driver vẫn hoạt động trước khi kiểm tra đăng nhập. URL: {current_url}")
            except Exception as e:
                print(f"Driver không hoạt động trước khi kiểm tra đăng nhập: {e}")
                self.status_update.emit(f"❌ Driver không hoạt động trước khi kiểm tra đăng nhập: {e}")
                return

            if self.is_logged_in():
                self.status_update.emit("✅ Đã đăng nhập bằng cookie từ file!")
                try:
                    print(f"Driver sau đăng nhập: {self.driver.current_url}")
                except Exception as e:
                    print(f"Driver bị đóng sau đăng nhập: {e}")
                    self.driver = self.setup_selenium_driver()
                    self.login_facebook_selenium()
                    
                self.driver.get(self.url)
                time.sleep(5)  # Chờ trang tải
                if "login" in self.driver.current_url:
                    self.status_update.emit("⚠️ Cookie không đủ quyền, yêu cầu đăng nhập lại")
                    os.remove('facebook_cookies.pkl')
                    self.login_facebook_selenium()
                    
                    
                return
            else:
                if os.path.exists('facebook_cookies.pkl'):
                    os.remove('facebook_cookies.pkl')
                    self.status_update.emit("⚠️ Cookie hết hạn, đã xóa file facebook_cookies.pkl.")

        self.status_update.emit("⌛ Vui lòng đăng nhập vào Facebook trong trình duyệt...")
        self.driver.get('https://m.facebook.com')
        try:
            WebDriverWait(self.driver, 300).until(
                EC.presence_of_element_located((By.XPATH, "//div[@role='tablist' and @data-type='container' and @data-mcomponent='MContainer' and contains(@class, 'm') and @data-actual-height]"))
            )
            self.status_update.emit("✅ Đăng nhập thành công!")
            cookies = self.driver.get_cookies()
            self.save_cookies(cookies)
            self.status_update.emit("✅ Đã lấy cookie thành công!")
            print("✅ Đã lấy cookie thành công!")
        except Exception as e:
            self.status_update.emit(f"❌ Lỗi khi chờ đăng nhập: {e}. Có thể người dùng chưa đăng nhập.")
            # self.driver.quit()
            # raise

    def fetch_page_content(self, url):
        self.status_update.emit(f"Đang thu thập email từ trang {url}")
        """Lấy nội dung HTML từ một trang và trích xuất email, dùng Selenium cho Facebook và requests cho các trang khác."""
        if self.main_window.is_facebook_url(url):
            # Nếu chưa có driver hoặc driver đã bị đóng, tạo mới
            if not hasattr(self, 'driver') or self.driver is None:
                self.login_facebook_selenium()  # Khởi tạo driver nếu chưa có
            else:
                try:
                    self.driver.current_url
                    print(1)
                except:
                    self.driver = self.setup_selenium_driver()
                    self.login_facebook_selenium()
            try:
                print(f"Điều hướng đến {url}")
                # Điều hướng đến URL được cung cấp
                self.driver.get(url)
                WebDriverWait(self.driver, 20).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )
                print("Trang đã tải hoàn tất")
                collected_emails = set()  # Tập hợp lưu email thu thập được
                collected_phones = set()  # Tập hợp lưu email thu thập được
                text_content_list = []  # Danh sách lưu nội dung văn bản
                see_more_xpath = """
                //div[@data-tracking-duration-id and @data-actual-height and @data-mcomponent='MContainer' and @data-type='container' and contains(@class, 'm')]
                /descendant::div[@data-type='container' and @data-focusable='true' and @data-tti-phase='-1' and @data-focusable='true' and @tabindex='0' and @data-action-id and @data-actual-height]
                /descendant::div[@data-mcomponent='TextArea' and @data-type='text' and @data-focusable='true' and @data-tti-phase='-1' and @data-focusable='true' and @tabindex='0' and @data-action-id]
                /div[@class='native-text' and @dir='auto']
                """

                # Lấy danh sách bài viết và cuộn theo scroll_times
                last_height = self.driver.execute_script("return document.body.scrollHeight")
                for i in range(self.scroll_times):
                    if not self.is_running:
                        break
                    # Cuộn đến cuối trang
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)  # Đợi trang tải nội dung mới
                    # Kiểm tra xem có nội dung mới không
                    new_height = self.driver.execute_script("return document.body.scrollHeight")
                    if new_height == last_height:
                        break  # Không có nội dung mới, dừng cuộn
                    last_height = new_height
                    # Nhấn "Xem thêm" nếu có
                    try:
                        see_more_buttons = self.driver.find_elements(By.XPATH, see_more_xpath)
                        for button in see_more_buttons:
                            if "... " in button.text:
                                self.driver.execute_script("arguments[0].click();", button)
                                time.sleep(1)
                    except:
                        pass
                    
                    html_content = self.driver.page_source
                    emails, phones = self.main_window.extract_emails_and_phones_from_html(html_content)
                    collected_emails.update(emails)  # Thêm email mới vào tập hợp (không trùng lặp)
                    collected_phones.update(phones)  # Thêm phone mới vào tập hợp (không trùng lặp)
                    self.emails.update(emails)  # Cập nhật tập hợp email
                    self.phones.update(phones)  # Cập nhật tập hợp số điện thoại
                    self.update_output.emit(self.emails, self.phones)  # Phát tín hiệu cập nhật
                    text_content_list.append(BeautifulSoup(html_content, 'html.parser').get_text(separator=" ").strip())
                text_content = "\n".join(text_content_list)
                return text_content, list(collected_emails), None
            except Exception as e:
                self.status_update.emit(f"❌ Lỗi khi thu thập từ Facebook: {e}")
                return None, [], None
        else:
            # Logic hiện tại cho các trang không phải Facebook
            html_content, error = self.main_window.fetch_html(url)
            if error or not html_content:
                return None, set(), None
            
            soup = BeautifulSoup(html_content, 'html.parser')
            # emails = self.main_window.extract_emails_and_phones_from_html(html_content)
            emails, phones = self.main_window.extract_emails_and_phones_from_html(html_content)
            self.emails.update(emails)  # Cập nhật tập hợp email
            self.phones.update(phones)  # Cập nhật tập hợp số điện thoại
            self.update_output.emit(self.emails, self.phones)
            text_content = soup.get_text(separator=" ").strip()
            
            # Tìm liên kết tiếp theo nếu có XPath
            next_url = None
            if self.xpath:
                tree = html.fromstring(html_content)
                next_elements = tree.xpath(self.xpath)
                if next_elements and hasattr(next_elements[0], 'get'):
                    next_url = next_elements[0].get('href')
                    if next_url and not next_url.startswith('http'):
                        next_url = urlparse(url)._replace(path=next_url).geturl()
            
            return text_content, emails, next_url

    def scroll_and_expand_posts(self, driver):
        """Cuộn trang theo từng bài viết và mở rộng nội dung."""
        see_more_xpath = """
                //div[@data-tracking-duration-id and @data-actual-height and @data-mcomponent='MContainer' and @data-type='container' and contains(@class, 'm')]
                /descendant::div[@data-type='container' and @data-focusable='true' and @data-tti-phase='-1' and @data-focusable='true' and @tabindex='0' and @data-action-id and @data-actual-height]
                /descendant::div[@data-mcomponent='TextArea' and @data-type='text' and @data-focusable='true' and @data-tti-phase='-1' and @data-focusable='true' and @tabindex='0' and @data-action-id]
                /div[@class='native-text' and @dir='auto']
                """
        try:
            last_height = self.driver.execute_script("return document.body.scrollHeight")  # Chiều cao trang ban đầu
            while True:
                # Tìm tất cả các bài viết
                posts = self.driver.find_elements(By.CSS_SELECTOR, "div.x1yztbdb.x1n2onr6.xh8yej3.x1ja2u2z")
                
                for post in posts:
                    # Cuộn đến vị trí của bài viết
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", post)
                    time.sleep(1)  # Đợi trang tải
                    
                    # Tìm và nhấp vào nút "Xem thêm" (nếu có)
                    try:
                        see_more_buttons = self.driver.find_elements(By.XPATH, see_more_xpath)
                        see_more_button.click()
                        time.sleep(1)  # Đợi nội dung tải
                    except NoSuchElementException:
                        pass  # Không có nút "Xem thêm"
                
                # Kiểm tra xem có cần cuộn tiếp không
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break  # Hết trang để cuộn
                last_height = new_height
                time.sleep(2)  # Đợi trang tải sau khi cuộn

        except Exception as e:
            print(f"Lỗi trong quá trình cuộn và mở rộng bài viết: {e}")
    
    def smooth_scroll_to_top(self):
        """Cuộn mượt lên đầu trang và kiểm tra đến khi đạt vị trí Y = 0."""
        self.driver.execute_script("""
            function smoothScrollUp() {
                let currentScroll = window.scrollY;
                function step() {
                    if (currentScroll > 0) {
                        window.scrollBy(0, -50);  // Cuộn lên 50px mỗi lần
                        currentScroll -= 50;
                        requestAnimationFrame(step);
                    }
                }
                step();
            }
            smoothScrollUp();
        """)

        # Chờ đến khi vị trí Y = 0
        max_attempts = 100  # Giới hạn số lần kiểm tra
        while max_attempts > 0:
            current_y = self.driver.execute_script("return window.scrollY")
            if current_y == 0:
                break  # Đã cuộn xong
            time.sleep(0.1)
            max_attempts -= 1

    def smooth_scroll_to_position(self, position):
        """Cuộn mượt đến vị trí ban đầu và kiểm tra đến khi đạt đúng vị trí."""
        self.driver.execute_script("""
            function smoothScrollDown(target) {
                let currentScroll = window.scrollY;
                function step() {
                    if (currentScroll < target) {
                        window.scrollBy(0, 50);  // Cuộn xuống 50px mỗi lần
                        currentScroll += 50;
                        requestAnimationFrame(step);
                    }
                }
                step();
            }
            smoothScrollDown(arguments[0]);
        """, position)

        # Chờ đến khi vị trí Y = position
        max_attempts = 100
        while max_attempts > 0:
            current_y = self.driver.execute_script("return window.scrollY")
            if abs(current_y - position) < 5:  # Chấp nhận sai số nhỏ
                break
            time.sleep(0.1)
            max_attempts -= 1
        time.sleep(3)

    def run(self):
        self.status_update.emit("♾️ Bắt đầu thu thập email...")
        try:
            executor = ThreadPoolExecutor(max_workers=self.max_workers)
            print(f"Khởi tạo ThreadPoolExecutor với {self.max_workers} workers")
            futures = []
            initial_url = self.convert_to_mbasic(self.url)
            print(f"URL đã chuyển đổi: {initial_url}")

            if self.main_window.is_facebook_url(self.url):
                print("Gọi fetch_page_content cho URL Facebook")
                content, emails, _ = self.fetch_page_content(self.url)
                print(f"Kết quả fetch: content={bool(content)}, emails={len(emails)}")
                if content:
                    self.content += content + "\n\n"
                    self.emails.update(emails)
                    self.content_signal.emit(self.content)
                else:
                    self.status_update.emit("⚠️ Không lấy được nội dung từ Facebook.")
            elif self.use_sitemap:
                sitemap_url = self.main_window.get_sitemap_url(self.url)
                if sitemap_url:
                    urls = self.main_window.parse_sitemap(sitemap_url)
                    futures = [executor.submit(self.main_window.process_url, u) for u in urls]
                else:
                    self.status_update.emit("⚠️ Không tìm thấy sitemap.")
                    self.finished.emit(set())
                    return
            else:
                futures.append(executor.submit(self.main_window.process_url, initial_url))

            if futures:
                for future in as_completed(futures):
                    if not self.is_running:
                        break
                    emails = future.result()
                    self.emails.update(emails)
                self.status_update.emit(f"✅ Thu thập hoàn tất! Tìm thấy {len(self.emails)} email.")
        except Exception as e:
            self.status_update.emit(f"❌ Lỗi trong quá trình thu thập: {e}")
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None
        if self.main_window.is_facebook_url(self.url):
            self.content_signal.emit(self.content)
        self.finished.emit(self.emails)

    def stop(self):
        """Dừng quá trình thu thập"""
        self.is_running = False

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(icon_path))  # Đặt biểu tượng cho ứng dụng
    window = BulkEmailSender()
    window.setWindowIcon(QIcon(icon_path))  # Đặt biểu tượng cho cửa sổ
    window.show()
    app.exec()
