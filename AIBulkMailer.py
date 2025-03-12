import smtplib
import ssl
import csv
import time
import random
import json
import sys
import os
import requests
import ctypes
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import msal
import re
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from openai import OpenAI
import groq
import google.generativeai as genai
from bs4 import BeautifulSoup
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QLineEdit, QTextEdit, QProgressBar, QComboBox, QTabWidget, QCheckBox
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import dns.resolver
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon, QIntValidator

SETTINGS_FILE = "settings.json"

# Cấu hình SMTP cho các nhà cung cấp có sẵn
SMTP_CONFIG = {
    "Gmail": {"server": "smtp.gmail.com", "port_ssl": 465, "port_tls": 587},
    "Yahoo": {"server": "smtp.mail.yahoo.com", "port_ssl": 465, "port_tls": 587},
    "Mailtrap": {"server": "live.smtp.mailtrap.io", "port_tls": 587},
    "AOL": {"server": "smtp.aol.com", "port_ssl": 465, "port_tls": 587},
    "Mailersend": {"server": "smtp.mailersend.net", "port_tls": 587},
    "Hotmail/Outlook": {"server": "smtp-mail.outlook.com", "port_ssl": 465, "port_tls": 587},
    "Yandex": {"server": "smtp.yandex.com", "port_ssl": 465, "port_tls": 587},
    "ZohoMail": {"server": "smtp.zoho.com", "port_ssl": 465, "port_tls": 587}
}

# Cấu hình Mô hình AI
AI_MODELS = {
    "ChatGPT": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4.5-preview", "o3-mini", "gpt-4o", "gpt-4o-mini", "whisper-1"],
    "Groq": ["distil-whisper-large-v3-en", "gemma2-9b-it", "llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama-guard-3-8b", "llama3-70b-8192", "llama3-8b-8192", "mixtral-8x7b-32768", "whisper-large-v3", "whisper-large-v3-turbo", "deepseek-r1-distill-qwen-32b", "deepseek-r1-distill-llama-70b-specdec", "qwen-qwq-32b", "mistral-saba-24b", "qwen-2.5-coder-32b", "qwen-2.5-32b", "deepseek-r1-distill-llama-70b", "llama-3.3-70b-specdec"],
    "Gemini": ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash", "gemini-1.5-flash-8b", "gemini-1.5-pro", "text-embedding-004"],
    "Grok": ["grok-2-1212", "grok-2-vision-1212"],
    "DeepSeek": ["deepseek-chat", "deepseek-reasoner", "deepseek-coder"]
}

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
    error_signal = pyqtSignal(str)
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    summary_signal = pyqtSignal(dict)

    # def __init__(self, smtp_server, port, sender_email, password, subject, body, recipients, connection_security, reply_to=None,
                 # use_oauth=False, oauth_config=None, refresh_token=None, auto_integration=False, ai_server=None, api_key=None, ai_prompt=None, model=None, min_delay=1, max_delay=5):
    def __init__(self, smtp_server, port, sender_email, password, subject, body, recipients, connection_security, reply_to=None, use_oauth=False, oauth_config=None, refresh_token=None, auto_integration=False, ai_server=None, api_key=None, ai_prompt=None, model=None, min_delay=None, max_delay=None):
        super().__init__()
        self.smtp_server = smtp_server
        self.port = port
        self.sender_email = sender_email
        self.password = password
        self.subject = subject
        self.body = body  # Mẫu nội dung cơ bản nếu không tích hợp AI
        self.recipients = recipients
        self.reply_to = reply_to
        self.connection_security = connection_security
        self.use_oauth = use_oauth  # Thêm cờ để bật/tắt OAuth2
        self.oauth_config = oauth_config  # Cấu hình OAuth2 (client_id, client_secret, token_url, ...)
        self.refresh_token = refresh_token  # Refresh token cho OAuth2
        self.is_sending = False
        self.should_stop = False
        # Các tham số AI:
        self.auto_integration = auto_integration
        self.ai_server = ai_server
        self.api_key = api_key
        self.ai_prompt = ai_prompt  # Prompt cơ bản từ giao diện
        self.model = model
        self.min_delay = min_delay
        self.max_delay = max_delay

    def stop(self):
        """Đặt cờ để dừng quá trình gửi email"""
        self.should_stop = True
    
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
                return response.choices[0].message.content
            elif self.ai_server == "Gemini":
                genai.configure(api_key=self.api_key)
                model_obj = genai.GenerativeModel(self.model)
                response = model_obj.generate_content(prompt)
                return response.text
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
                    messages=[{"role": "user", "content": prompt}]
                )
                raw_content = response.choices[0].message.content
                cleaned_content = self.remove_think_tags(raw_content)  # Xóa phần <think>
                cleaned_content = re.sub(r"^```(?:html)?\n?|```$", "", cleaned_content, flags=re.MULTILINE)  # Loại bỏ dấu ```
                return cleaned_content.strip()  # Loại bỏ khoảng trắng thừa
            elif self.ai_server == "Grok":
                return "Grok chưa có API công khai, hãy kiểm tra sau!"
            else:
                return self.body  # Fallback
        except Exception as e:
            # Nếu có lỗi khi gọi API, dùng mẫu nội dung gốc
            return self.body
    
    def run(self):
        failures = {}
        successes = 0
        try:
            start_time = time.time()
            timeout = 300  # Giới hạn thời gian 5 phút
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
                if self.should_stop:
                    self.error_signal.emit("⛔ Quá trình gửi email đã bị dừng.")
                    return
                if time.time() - start_time > timeout:
                    self.error_signal.emit("⛔ Quá trình gửi email vượt quá thời gian cho phép.")
                    return
                    
                # Nếu auto_integration được bật, tạo nội dung mới cho mỗi email
                if self.auto_integration:
                    unique_body = self.generate_unique_content(recipient)
                else:
                    unique_body = self.body
                    
                try:
                    msg = MIMEMultipart()
                    msg['From'] = self.sender_email
                    msg['To'] = recipient
                    msg['Subject'] = self.subject
                    if self.reply_to:
                        msg['Reply-To'] = self.reply_to
                    msg.attach(MIMEText(unique_body, 'html'))
                    server.sendmail(self.sender_email, recipient, msg.as_string())
                    successes += 1
                    self.log_signal.emit(f"✅ Email được gửi tới {recipient}")
                except Exception as ex:
                    failures[recipient] = str(ex)
                    self.log_signal.emit(f"❌ Gửi mail không thành công tới {recipient}: {ex}")
                finally:
                    self.progress_signal.emit(idx + 1)
                    
                # Thời gian chờ ngẫu nhiên giữa các lần gửi
                delay_time = random.uniform(self.min_delay, self.max_delay)
                self.log_signal.emit(f"⏳ Đang chờ {delay_time:.2f} giây trước khi gửi mail tiếp theo...")
                time.sleep(delay_time)
                
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

    def __init__(self, ai_server, api_key, prompt, model):
        super().__init__()
        self.ai_server = ai_server
        self.api_key = api_key
        self.prompt = prompt
        self.model = model
    
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
                generated = response.choices[0].message.content
            elif self.ai_server == "Gemini":
                genai.configure(api_key=self.api_key)
                model = genai.GenerativeModel(self.model)
                response = model.generate_content(self.prompt)
                generated = response.text
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
            self.result_signal.emit(generated)
        except Exception as e:
            self.error_signal.emit(f"Lỗi khi gọi AI: {str(e)}")
        finally:
            QThread.currentThread().quit()  # Thêm dòng này để đảm bảo thread dừng an toàn

# ---------------- Main Application ---------------- #
class BulkEmailSender(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.load_settings()
        self.is_sending = False
        self.is_gathering = False
        self.extracted_emails = set()
        # Gọi delayed_save_settings() mỗi khi người dùng nhập dữ liệu
        self.email_input.textChanged.connect(self.delayed_save_settings)
        self.password_input.textChanged.connect(self.delayed_save_settings)
        self.subject_input.textChanged.connect(self.delayed_save_settings)
        self.reply_input.textChanged.connect(self.delayed_save_settings)
        self.provider_combo.currentIndexChanged.connect(self.delayed_save_settings)
        self.custom_smtp_input.textChanged.connect(self.delayed_save_settings)
        self.custom_port_input.textChanged.connect(self.delayed_save_settings)
        self.rich_editor.textChanged.connect(self.delayed_save_settings)
        self.raw_editor.textChanged.connect(self.delayed_save_settings)
        self.min_delay_input.textChanged.connect(self.delayed_save_settings)
        self.max_delay_input.textChanged.connect(self.delayed_save_settings)
        self.ai_server_combo.currentIndexChanged.connect(self.delayed_save_settings)
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

    def initUI(self):
        # Lấy đường dẫn file logo.ico
        if hasattr(sys, "_MEIPASS"):  # Nếu chạy từ file .exe
            icon_path = os.path.join(sys._MEIPASS, "logo.ico")
        else:  # Nếu chạy trực tiếp bằng Python
            icon_path = "logo.ico"
        self.setWindowIcon(QIcon(icon_path))  # Đặt icon cho cửa sổ
        
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
        self.provider_combo.addItems(list(SMTP_CONFIG.keys()) + ["Khác"])
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
        self.ai_server_combo.addItems(["Groq", "ChatGPT", "Gemini", "Grok", "DeepSeek"])
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
            "Phần mềm": "AIBulkMailer",
            "Phiên bản": "1.1.0",
            "Ngày phát hành": "12/03/2025",
            "Mô tả": "Phần mềm gửi email hàng loạt với khả năng hỗ trợ đa luồng, tạo nội dung tự động bằng nhiều mô hình AI và thu thập tất cả email trên một trang web."
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
    
    def stop_sending(self):
        if self.is_sending and self.worker:
            self.worker.stop()  # Gọi phương thức stop của worker
            self.thread.quit()  # Thoát luồng
            self.thread.wait()  # Đợi luồng dừng hoàn toàn
            self.thread = None  # Xóa tham chiếu đến luồng cũ
            self.is_sending = False
            self.status_label.setText("⛔ Quá trình gửi email đã bị dừng.")
            self.send_button.setEnabled(True)
            self.stop_sending_button.setEnabled(False)
    
    def setup_gather_tab(self):
        """Thiết lập tab Gather Mail."""
        self.gather_tab = QWidget()
        layout = QVBoxLayout()

        # Ô nhập link trang web
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Nhập link trang web")
        layout.addWidget(self.url_input)

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
        url = self.url_input.text().strip()
        if not url:
            self.output_area.setText("⚠️ Vui lòng nhập link trang web.")
            return

        try:
            max_workers = int(self.thread_count_input.text().strip())
            if max_workers <= 0:
                raise ValueError
        except ValueError:
            self.output_area.setText("⚠️ Số luồng không hợp lệ. Vui lòng nhập số nguyên dương.")
            return

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
        self.worker = GatherEmailsWorker(self, url, self.sitemap_checkbox.isChecked(), max_workers)
        self.worker.moveToThread(self.thread)

        # Kết nối tín hiệu
        self.thread.started.connect(self.worker.run)
        self.worker.status_update.connect(lambda msg: self.gather_status_label.setText(msg))
        self.worker.finished.connect(self.on_gather_finished)
        self.worker.finished.connect(self.cleanup_thread)

        self.thread.start()

    def on_gather_finished(self, emails):
        """Xử lý khi quá trình thu thập email hoàn tất"""
        self.extracted_emails = emails
        self.output_area.setText("\n".join(emails) if emails else "️⚠️ Không tìm thấy email nào.")
        # self.gather_status_label.setText(f"✅ Hoàn tất! Thu thập {len(emails)} email.")
        self.gather_button.setEnabled(True)
        self.stop_gathering_button.setEnabled(False)
        self.export_button.setEnabled(bool(emails))
        
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
        emails = set(self.extract_emails_from_html(html))
        return emails

    def stop_gathering(self):
        """Dừng tiến trình thu thập email"""
        if hasattr(self, 'worker') and self.worker:
            self.worker.stop()
        
        if hasattr(self, 'thread') and self.thread and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()

        self.gather_status_label.setText("⛔ Quá trình thu thập đã bị dừng.")
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

    def parse_sitemap(self, sitemap_url):
        """Phân tích sitemap và trả về danh sách các URL, bao gồm sitemap con."""
        urls = []
        try:
            response = requests.get(sitemap_url, timeout=10)
            if response.status_code != 200:
                # self.output_area.setText(f"❌ Không thể tải sitemap: {response.status_code}")
                return []

            # self.status_label.setText("♾️ Đang trích xuất tất cả liên kết bên trong sitemap")
            content = response.content.decode('utf-8', errors='ignore')
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
            return response.text, None
        except requests.exceptions.RequestException as e:
            return None, str(e)
        
    def extract_emails_from_html(self, html):
        """Trích xuất email từ mã HTML một cách chính xác hơn."""
        soup = BeautifulSoup(html, 'html.parser')
        emails = set()

        # Lấy email từ liên kết mailto
        for a in soup.find_all('a', href=True):
            if a['href'].startswith('mailto:'):
                email = a['href'][7:].split('?')[0]
                # Kiểm tra email bằng biểu thức regex chặt chẽ
                if re.fullmatch(r'(?<!\S)[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?!\S)', email):
                    emails.add(email)

        # Lấy email từ văn bản thông qua get_text()
        # Dùng separator=" " để đảm bảo các đoạn văn bản được ngăn cách bằng khoảng trắng
        text = soup.get_text(separator=" ")
        found = re.findall(r'(?<!\S)[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?!\S)', text)
        emails.update(found)
        return emails
    
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
        models = AI_MODELS.get(ai_server, [])  # Lấy danh sách model tương ứng
        self.model_combo.clear()  # Xóa danh sách model cũ
        self.model_combo.addItems(models)  # Thêm danh sách model mới

    def update_smtp_provider(self):
        """Tự động chọn SMTP dựa trên tên miền email."""
        email = self.email_input.text().strip()
        if '@' in email:
            domain = email.split('@')[1].lower()
            for provider, config in SMTP_CONFIG.items():
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
            config = SMTP_CONFIG.get(provider)
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

        self.thread = QThread()
        # self.worker = EmailSenderWorker(smtp_server, port, sender_email, password, subject, body, self.recipients, connection_security, reply_to, use_oauth=use_oauth, oauth_config=oauth_config, refresh_token=refresh_token, auto_integration=auto_integration, ai_server=ai_server, api_key=api_key, ai_prompt=ai_prompt, model=model)
        self.worker = EmailSenderWorker(smtp_server, port, sender_email, password, subject, body, self.recipients, connection_security, reply_to, use_oauth=use_oauth, oauth_config=oauth_config, refresh_token=refresh_token, auto_integration=auto_integration, ai_server=ai_server, api_key=api_key, ai_prompt=ai_prompt, model=model, min_delay=min_delay, max_delay=max_delay)
        self.worker.moveToThread(self.thread)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.log_signal.connect(lambda msg: self.log_output.append(msg))
        self.worker.summary_signal.connect(self.on_summary)
        self.worker.error_signal.connect(self.on_error)
        self.thread.started.connect(self.worker.run)
        self.worker.summary_signal.connect(self.thread.quit)
        self.worker.summary_signal.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(lambda: self.stop_sending_button.setEnabled(False))
        self.thread.finished.connect(lambda: self.send_button.setEnabled(True))
        self.thread.finished.connect(lambda: setattr(self, 'is_sending', False))  # Reset flag khi luồng hoàn thành
        self.thread.start()
        QApplication.processEvents()

    def on_error(self, error_msg):
        self.status_label.setText(f"❌ Lỗi: {error_msg}")
        self.log_output.append(f"❌ Lỗi: {error_msg}")
        self.send_button.setEnabled(True)
        # Nếu thread vẫn đang chạy, hãy dừng nó
        if self.thread is not None and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()
            self.thread.deleteLater()
            self.thread = None
        self.is_sending = False  # Reset flag khi có lỗi

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
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait()
            self.thread.deleteLater()
            self.thread = None
        self.send_button.setEnabled(True)
        self.is_sending = False  # Reset flag khi hoàn thành

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

        self.gen_status_label.setText("♾️ Đang tạo nội dung...")
        self.generate_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        # Tạo luồng mới
        self.gen_thread = QThread()
        self.gen_worker = ContentGeneratorWorker(ai_server, api_key, prompt, model)
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
                self.email_input.setText(settings.get("email", ""))
                self.password_input.setText(settings.get("password", ""))
                self.subject_input.setText(settings.get("subject", ""))
                self.reply_input.setText(settings.get("reply_to", ""))
                self.provider_combo.setCurrentIndex(settings.get("smtp_provider_index", 0))
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
                self.sitemap_checkbox.setChecked(settings.get("sitemap", False))
                self.thread_count_input.setText(settings.get("thread_count", "5"))
                # Load settings từ file hoặc cấu hình
                ai_server = settings.get("ai_server", "ChatGPT")
                model = settings.get("model", "")
                self.ai_server_combo.setCurrentText(ai_server)
                self.update_model_combo()  # Cập nhật danh sách model
                if model in AI_MODELS.get(ai_server, []):
                    self.model_combo.setCurrentText(model)  # Đặt model đã lưu
                self.oauth_checkbox.setChecked(settings.get("use_oauth", False))
                self.client_id_input.setText(settings.get("client_id", ""))
                self.client_secret_input.setText(settings.get("client_secret", ""))
                self.refresh_token_input.setText(settings.get("refresh_token", ""))
                self.toggle_oauth_fields(Qt.CheckState.Checked.value if settings.get("use_oauth", False) else Qt.CheckState.Unchecked.value)
            except Exception as e:
                if hasattr(self, 'status_label'):
                    self.status_label.setText(f"❌ Lỗi khi tải các thiết lập: {e}")

    def save_settings(self):
        if self.tab_widget.currentIndex() == 1:
            self.rich_editor.setHtml(self.raw_editor.toPlainText())
        
        settings = {
            "email": self.email_input.text(),
            "password": self.password_input.text(),
            "subject": self.subject_input.text(),
            "reply_to": self.reply_input.text(),
            "smtp_provider_index": self.provider_combo.currentIndex(),
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
            "connection_security": self.security_combo.currentText(),
            "check_email": self.check_email_checkbox.isChecked(),
            "gather_url": self.url_input.text(),
            "sitemap": self.sitemap_checkbox.isChecked(),
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
    status_update = pyqtSignal(str)  # Tín hiệu cập nhật trạng thái

    def __init__(self, main_window, url, use_sitemap, max_workers):
        super().__init__()
        self.main_window = main_window  # Truy cập hàm từ BulkEmailSender
        self.url = url
        self.use_sitemap = use_sitemap
        self.max_workers = max_workers
        self.is_running = True
        self.emails = set()

    def run(self):
        """Bắt đầu quá trình thu thập email"""
        self.status_update.emit("♾️ Bắt đầu thu thập email...")

        try:
            executor = ThreadPoolExecutor(max_workers=self.max_workers)
            futures = []

            if self.use_sitemap:
                sitemap_url = self.main_window.get_sitemap_url(self.url)
                if sitemap_url:
                    urls = self.main_window.parse_sitemap(sitemap_url)
                    futures = [executor.submit(self.main_window.process_url, u) for u in urls]
                else:
                    self.status_update.emit("⚠️ Không tìm thấy sitemap.")
                    self.finished.emit(set())
                    return
            else:
                futures.append(executor.submit(self.main_window.process_url, self.url))

            # Theo dõi tiến trình
            for future in as_completed(futures):
                if not self.is_running:
                    break
                emails = future.result()
                self.emails.update(emails)

            self.status_update.emit(f"✅ Thu thập hoàn tất! Tìm thấy {len(self.emails)} email.")
        except Exception as e:
            self.status_update.emit(f"❌ Lỗi trong quá trình thu thập: {e}")
        
        self.finished.emit(self.emails)


    def stop(self):
        """Dừng quá trình thu thập"""
        self.is_running = False

if __name__ == "__main__":
    # app = QApplication([])
    app = QApplication(sys.argv)
    
    # Đặt icon cho Taskbar khi ứng dụng chạy
    if hasattr(sys, "_MEIPASS"):
        icon_path = os.path.join(sys._MEIPASS, "logo.ico")
    else:
        icon_path = "logo.ico"

    app.setWindowIcon(QIcon(icon_path))  # Đặt biểu tượng cho ứng dụng
    window = BulkEmailSender()
    window.setWindowIcon(QIcon(icon_path))  # Đặt biểu tượng cho cửa sổ
    window.show()
    app.exec()
