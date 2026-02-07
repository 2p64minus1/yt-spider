import sys
import os
import logging
import time
import subprocess
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QPushButton, QLabel, QProgressBar, QTextEdit,
                             QMessageBox, QButtonGroup, QFrame, QScrollArea, QDialog,
                             QDialogButtonBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QPixmap, QPalette, QCloseEvent
import yt_dlp
import requests
from io import BytesIO
#兼容防止报错
if sys.platform == "win32":
    import ctypes

    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_file = os.path.join(log_dir, f"youtube_downloader_{time.strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DisclaimerDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        #一定要看免责声明啊
        self.setWindowTitle("免责声明")
        self.setFixedSize(600, 400)

        layout = QVBoxLayout(self)

        # 免责声明文本
        disclaimer_text = self.load_disclaimer_text()
        text_edit = QTextEdit()
        text_edit.setPlainText(disclaimer_text)
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet("""
            QTextEdit {
                font-family: 'Microsoft YaHei';
                font-size: 12px;
                line-height: 1.5;
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 10px;
                background-color: #f9f9f9;
            }
        """)
        layout.addWidget(text_edit)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        button_box.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                font-size: 12px;
                border: 1px solid #4CAF50;
                background-color: #4CAF50;
                color: white;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        layout.addWidget(button_box)

    def load_disclaimer_text(self):
        try:
            if os.path.exists("mzsm.txt"):
                with open("mzsm.txt", "r", encoding="utf-8") as f:
                    return f.read()
            else:
                # 如果文件不存在，使用默认免责声明
                return self.get_default_disclaimer()
        except Exception as e:
            logging.error(f"加载免责声明文件失败: {e}")
            return self.get_default_disclaimer()

    def get_default_disclaimer(self):
        return """免责声明

本文档适用于所有观看本人视频、使用本人代码或接触本人创作内容的用户。
请仔细阅读并理解以下声明。特此郑重声明：1.此程序以及程序下的所有子
程序和文件仅用于学习与研究，下载的文件请在24小时内删除，如有侵权，
与本人无关2.  政治立场：本人及本视频/代码/内容完全支持中国共产党，
拥护中国共产党的领导，遵守中华人民共和国法律法规，积极践行社会主义核
心价值观。3.  通信规范：本人确认，没有在QQ空间、微信朋友圈、微博、
知乎或任何其他地球及非地球社交平台向三体人、外星文明或任何异次元生命体
发送过地球坐标、人类文明概要或任何可能危及地球安全的信息。4.  内容性
质：本视频/代码/音频/文档仅供参考，不构成任何形式的专业建议、承诺或保
证。所有内容均基于制作时的个人理解和有限知识，仅代表个人观点，不代表任何
组织、公司或平台的立场。5.  教育经历澄清：本内容不能也无意证明你的小学
及初中副科（如美术、音乐、体育、思想品德等）被班主任或其他教师霸占。学生
时代的经历因人而异，请理性看待。6.  关于“歧视”的全面否定：本人内容旨在
技术分享，绝无任何商业用途，文中提到的所有“本人”皆是zzy，如程序bug
发送邮件到“github@ik.me"""


class DownloadThread(QThread):
    progress_updated = pyqtSignal(int, str)
    download_finished = pyqtSignal(dict)
    download_error = pyqtSignal(str)
    info_ready = pyqtSignal(dict)

    def __init__(self, url, resolution=None):
        super().__init__()
        self.url = url
        self.resolution = resolution
        self.is_cancelled = False

    def run(self):
        try:
            ydl_opts_info = {
                'quiet': True,
                'no_warnings': False,
            }

            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info_dict = ydl.extract_info(self.url, download=False)
                self.info_ready.emit(info_dict)
                if self.is_cancelled:
                    return


                ydl_opts = {
                    'outtmpl': 'downloads/%(title)s.%(ext)s',
                    'quiet': True,
                    'no_warnings': False,
                    'progress_hooks': [self.progress_hook],
                }
                ffmpeg_path = self.find_ffmpeg()
                if ffmpeg_path:
                    ydl_opts['ffmpeg_location'] = ffmpeg_path
                    logging.info(f"使用FFmpeg路径: {ffmpeg_path}")
                if self.resolution:
                    if self.resolution == '480p':
                        ydl_opts['format'] = 'best[height<=480]/best'
                    elif self.resolution == '720p':
                        ydl_opts['format'] = 'best[height<=720]/best'
                    elif self.resolution == '1080p':
                        ydl_opts['format'] = 'best[height<=1080]/best'
                    else:
                        ydl_opts['format'] = 'best'
                else:
                    ydl_opts['format'] = 'best'

                # 确保下载目录存在
                if not os.path.exists('downloads'):
                    os.makedirs('downloads')

                # 开始下载
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([self.url])

        except Exception as e:
            self.download_error.emit(str(e))

    def find_ffmpeg(self):
        """查找ffmpeg可执行文件"""
        # 检查当前目录下的ffmpeg文件夹
        possible_paths = [
            './ffmpeg/bin/ffmpeg.exe',  # Windows
            './ffmpeg/ffmpeg.exe',  # Windows备用路径
            './ffmpeg/bin/ffmpeg',  # Linux/Mac
            './ffmpeg/ffmpeg',  # Linux/Mac备用路径
            'ffmpeg',  # 系统PATH中的ffmpeg
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return os.path.abspath(path)

        # 如果找不到，尝试在系统PATH中查找
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
            if result.returncode == 0:
                return 'ffmpeg'
        except:
            pass

        logging.warning("未找到FFmpeg，某些格式转换功能可能受限")
        return None

    def progress_hook(self, d):
        if self.is_cancelled:
            raise Exception("下载已取消")

        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            if total:
                percent = int((d['downloaded_bytes'] / total) * 100)
                speed = d.get('_speed_str', 'N/A')
                self.progress_updated.emit(percent, f"下载中: {percent}% - 速度: {speed}")
        elif d['status'] == 'finished':
            self.progress_updated.emit(100, "下载完成！")
            self.download_finished.emit(d)

    def cancel(self):
        self.is_cancelled = True


class ScrollableLabel(QWidget):
    """可滚动的标签组件"""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.text = text
        self.init_ui()
        self.animation = None

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel(self.text)
        self.label.setStyleSheet("""
            QLabel {
                color: #333;
                padding: 5px;
                font-size: 14px;
                font-weight: bold;
            }
        """)

        # 创建滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #ddd;
                background-color: #f9f9f9;
                border-radius: 4px;
            }
        """)
        self.scroll_area.setFixedHeight(40)
        self.scroll_area.setWidget(self.label)

        layout.addWidget(self.scroll_area)

    def set_text(self, text):
        """设置文本并启动滚动动画（如果需要）"""
        self.text = text
        self.label.setText(text)

        # 检查文本长度是否需要滚动
        self.start_scroll_animation_if_needed()

    def start_scroll_animation_if_needed(self):
        """如果文本过长，启动滚动动画"""
        # 获取文本宽度
        text_width = self.label.fontMetrics().boundingRect(self.text).width()
        scroll_width = self.scroll_area.width() - 10  # 减去边距

        if text_width > scroll_width:
            # 文本过长，需要滚动，自动或手动滚动
            if self.animation:
                self.animation.stop()

            self.animation = QPropertyAnimation(self.scroll_area.horizontalScrollBar(), b"value")
            self.animation.setDuration(5000)  # 5秒完成一次滚动
            self.animation.setStartValue(0)
            self.animation.setEndValue(self.scroll_area.horizontalScrollBar().maximum())
            self.animation.setLoopCount(-1)  # 无限循环
            self.animation.setEasingCurve(QEasingCurve.InOutQuad)
            self.animation.start()
        else:
            # 文本不长，停止动画并重置位置
            if self.animation:
                self.animation.stop()
            self.scroll_area.horizontalScrollBar().setValue(0)


class YouTubeDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.download_thread = None
        self.current_video_info = None
        self.version = "V3.0"  # 版本号
        self.is_downloading = False
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f'YouTube 视频下载器 - {self.version}')
        self.setFixedSize(900, 600)

        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QHBoxLayout(central_widget)

        # 左侧面板 - 视频信息
        left_panel = QVBoxLayout()
        left_panel.setContentsMargins(10, 10, 10, 10)

        # 缩略图
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(320, 180)
        self.thumbnail_label.setStyleSheet("""
            border: 1px solid #ccc; 
            background-color: #f0f0f0;
            border-radius: 8px;
        """)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setText("视频缩略图")
        left_panel.addWidget(self.thumbnail_label)

        # 视频信息容器
        info_container = QFrame()
        info_container.setStyleSheet("""
            QFrame {
                background-color: #f9f9f9;
                border: 1px solid #ddd;
                border-radius: 8px;
                margin-top: 10px;
            }
        """)
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(10, 10, 10, 10)
        info_layout.setSpacing(8)

        # 可滚动的标题
        title_label = QLabel("视频标题:")
        title_label.setStyleSheet("font-weight: bold; color: #555;")
        info_layout.addWidget(title_label)

        self.title_scroll_label = ScrollableLabel("等待加载视频标题...")
        info_layout.addWidget(self.title_scroll_label)

        # 版本号显示
        version_layout = QHBoxLayout()
        version_layout.addStretch()
        self.version_label = QLabel(self.version)
        self.version_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 12px;
                font-style: italic;
                padding: 2px 8px;
                background-color: #e0e0e0;
                border-radius: 10px;
            }
        """)
        version_layout.addWidget(self.version_label)
        info_layout.addLayout(version_layout)

        # 其他视频信息
        self.details_label = QLabel("选择视频并开始下载以显示详细信息")
        self.details_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 12px;
                padding: 8px;
                background-color: #f0f0f0;
                border-radius: 4px;
                margin-top: 5px;
            }
        """)
        self.details_label.setWordWrap(True)
        self.details_label.setFixedHeight(60)
        info_layout.addWidget(self.details_label)

        left_panel.addWidget(info_container)

        # 右侧面板
        right_panel = QVBoxLayout()

        # URL 输入
        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("请输入 YouTube 视频链接")
        self.url_input.setStyleSheet("""
            QLineEdit {
                padding: 10px;
                font-size: 14px;
                border: 2px solid #ddd;
                border-radius: 6px;
            }
            QLineEdit:focus {
                border-color: #4CAF50;
            }
        """)
        url_layout.addWidget(self.url_input)
        right_panel.addLayout(url_layout)

        # 分辨率选择按钮
        resolution_layout = QHBoxLayout()
        self.resolution_group = QButtonGroup(self)

        self.btn_480p = QPushButton('480P')
        self.btn_720p = QPushButton('720P')
        self.btn_1080p = QPushButton('1080P')
        self.btn_download = QPushButton('下载')
        self.btn_disclaimer = QPushButton('免责声明')  # 免责声明按钮
        self.btn_exit = QPushButton('退出')

        # 设置按钮样式
        button_style = """
            QPushButton {
                padding: 12px;
                font-size: 14px;
                border: 2px solid #ccc;
                background-color: #f8f8f8;
                border-radius: 6px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
                border-color: #aaa;
            }
            QPushButton:pressed {
                background-color: #d8d8d8;
            }
            QPushButton:checked {
                background-color: #4CAF50;
                color: white;
                border-color: #2E7D32;
            }
        """

        self.btn_480p.setCheckable(True)
        self.btn_720p.setCheckable(True)
        self.btn_1080p.setCheckable(True)

        self.btn_480p.setStyleSheet(button_style)
        self.btn_720p.setStyleSheet(button_style)
        self.btn_720p.setChecked(True)  # 默认选择720P
        self.btn_1080p.setStyleSheet(button_style)
        self.btn_download.setStyleSheet("""
            QPushButton {
                padding: 12px;
                font-size: 14px;
                border: 2px solid #2E7D32;
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #45a049;
                border-color: #1B5E20;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #a5d6a7;
                border-color: #81c784;
                color: #e8f5e9;
            }
        """)

        # 免责声明按钮样式
        self.btn_disclaimer.setStyleSheet("""
            QPushButton {
                padding: 12px;
                font-size: 14px;
                border: 2px solid #FF9800;
                background-color: #FFC107;
                color: #333;
                font-weight: bold;
                border-radius: 6px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #FFB300;
                border-color: #F57C00;
            }
            QPushButton:pressed {
                background-color: #FFA000;
            }
        """)

        # 退出按钮样式
        self.btn_exit.setStyleSheet("""
            QPushButton {
                padding: 12px;
                font-size: 14px;
                border: 2px solid #d32f2f;
                background-color: #f44336;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #e53935;
                border-color: #c62828;
            }
            QPushButton:pressed {
                background-color: #d32f2f;
            }
        """)

        resolution_layout.addWidget(self.btn_480p)
        resolution_layout.addWidget(self.btn_720p)
        resolution_layout.addWidget(self.btn_1080p)
        resolution_layout.addWidget(self.btn_download)
        resolution_layout.addWidget(self.btn_disclaimer)
        resolution_layout.addWidget(self.btn_exit)

        self.resolution_group.addButton(self.btn_480p)
        self.resolution_group.addButton(self.btn_720p)
        self.resolution_group.addButton(self.btn_1080p)

        right_panel.addLayout(resolution_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #ddd;
                border-radius: 6px;
                text-align: center;
                height: 25px;
                font-size: 12px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 4px;
            }
        """)
        right_panel.addWidget(self.progress_bar)

        # 状态标签
        self.status_label = QLabel("等待下载...")
        self.status_label.setStyleSheet("""
            padding: 8px; 
            color: #666;
            background-color: #f0f0f0;
            border-radius: 4px;
            font-size: 13px;
        """)
        right_panel.addWidget(self.status_label)

        # 日志输出
        log_label = QLabel("下载日志:")
        log_label.setStyleSheet("font-weight: bold; margin-top: 10px; color: #555;")
        right_panel.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(200)
        self.log_text.setStyleSheet("""
            QTextEdit {
                font-family: 'Courier New'; 
                font-size: 11px;
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 5px;
                background-color: #fafafa;
            }
        """)
        self.log_text.setReadOnly(True)
        right_panel.addWidget(self.log_text)

        # 添加到主布局
        main_layout.addLayout(left_panel, 40)
        main_layout.addLayout(right_panel, 60)

        # 连接信号和槽
        self.btn_download.clicked.connect(self.start_download)
        self.btn_disclaimer.clicked.connect(self.show_disclaimer)  # 连接免责声明按钮
        self.btn_exit.clicked.connect(self.safe_exit)

        # 初始化日志
        self.log_message("程序已启动，等待用户输入...")
        self.log_message(f"当前版本: {self.version}")
        self.log_message(f"日志文件: {log_file}")

        # 检查ffmpeg是否存在
        self.check_ffmpeg()

    def check_ffmpeg(self):
        """检查ffmpeg是否可用"""
        try:
            ffmpeg_path = self.find_ffmpeg()
            if ffmpeg_path:
                self.log_message(f"FFmpeg已找到: {ffmpeg_path}")
                # 测试ffmpeg是否工作正常
                result = subprocess.run([ffmpeg_path, '-version'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    self.log_message("FFmpeg工作正常")
                else:
                    self.log_message("FFmpeg测试失败")
            else:
                self.log_message("警告: 未找到FFmpeg，某些功能可能受限")
        except Exception as e:
            self.log_message(f"FFmpeg检查失败: {e}")

    def find_ffmpeg(self):
        """查找ffmpeg可执行文件"""
        # 检查当前目录下的ffmpeg文件夹
        possible_paths = [
            './ffmpeg/bin/ffmpeg.exe',  # Windows
            './ffmpeg/ffmpeg.exe',  # Windows备用路径
            './ffmpeg/bin/ffmpeg',  # Linux/Mac
            './ffmpeg/ffmpeg',  # Linux/Mac备用路径
            'ffmpeg',  # 系统PATH中的ffmpeg
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return os.path.abspath(path)

        # 如果找不到，尝试在系统PATH中查找
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
            if result.returncode == 0:
                return 'ffmpeg'
        except:
            pass

        return None

    def show_disclaimer(self):
        """显示免责声明"""
        dialog = DisclaimerDialog(self)
        dialog.exec_()

    def get_selected_resolution(self):
        """获取选择的分辨率"""
        if self.btn_480p.isChecked():
            return '480p'
        elif self.btn_720p.isChecked():
            return '720p'
        elif self.btn_1080p.isChecked():
            return '1080p'
        else:
            return None

    def start_download(self):
        """开始下载视频"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "输入错误", "请输入YouTube视频链接！")
            return

        resolution = self.get_selected_resolution()
        if not resolution:
            QMessageBox.warning(self, "选择错误", "请选择视频分辨率！")
            return

        # 禁用按钮
        self.set_buttons_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.is_downloading = True

        # 创建并启动下载线程
        self.download_thread = DownloadThread(url, resolution)
        self.download_thread.progress_updated.connect(self.update_progress)
        self.download_thread.download_finished.connect(self.download_finished)
        self.download_thread.download_error.connect(self.download_error)
        self.download_thread.info_ready.connect(self.video_info_ready)
        self.download_thread.start()

        self.log_message(f"开始下载: {url}")
        self.log_message(f"选择分辨率: {resolution}")

    def set_buttons_enabled(self, enabled):
        """设置按钮启用状态"""
        self.btn_download.setEnabled(enabled)
        self.btn_480p.setEnabled(enabled)
        self.btn_720p.setEnabled(enabled)
        self.btn_1080p.setEnabled(enabled)
        self.btn_disclaimer.setEnabled(enabled)
        self.btn_exit.setEnabled(enabled)

    def update_progress(self, percent, status):
        """更新下载进度"""
        self.progress_bar.setValue(percent)
        self.status_label.setText(status)
        self.log_message(status)

    def download_finished(self, info):
        """下载完成"""
        self.set_buttons_enabled(True)
        self.is_downloading = False
        self.status_label.setText("下载完成！")
        self.log_message(f"文件已保存到: {info.get('filename', '未知')}")
        QMessageBox.information(self, "完成", "视频下载完成！")

    def download_error(self, error_msg):
        """下载错误处理"""
        self.set_buttons_enabled(True)
        self.is_downloading = False
        self.status_label.setText("下载出错！")
        self.log_message(f"错误: {error_msg}")
        QMessageBox.critical(self, "错误", f"下载过程中出现错误:\n{error_msg}")

    def video_info_ready(self, info_dict):
        """视频信息获取完成"""
        self.current_video_info = info_dict

        # 显示缩略图
        thumbnail_url = info_dict.get('thumbnail')
        if thumbnail_url:
            try:
                response = requests.get(thumbnail_url)
                pixmap = QPixmap()
                pixmap.loadFromData(BytesIO(response.content).read())
                self.thumbnail_label.setPixmap(pixmap.scaled(320, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except Exception as e:
                self.log_message(f"加载缩略图失败: {str(e)}")

        # 显示视频信息
        title = info_dict.get('title', '未知标题')
        duration = info_dict.get('duration', 0)
        uploader = info_dict.get('uploader', '未知上传者')

        # 设置可滚动标题
        self.title_scroll_label.set_text(title)

        # 显示详细信息
        selected_resolution = self.get_selected_resolution()
        minutes, seconds = divmod(duration, 60)
        duration_str = f"{minutes:02d}:{seconds:02d}"

        details_text = f"""
        <b>上传者:</b> {uploader}<br>
        <b>时长:</b> {duration_str}<br>
        <b>选择分辨率:</b> {selected_resolution}<br>
        <b>音频质量:</b> 最高质量
        """
        self.details_label.setText(details_text)
        self.log_message(f"视频信息加载完成: {title}")

    def log_message(self, message):
        """添加日志消息"""
        self.log_text.append(f"{message}")
        # 自动滚动到底部
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def safe_exit(self):
        """安全退出程序"""
        if self.is_downloading:
            reply = QMessageBox.question(self, '确认退出',
                                         '下载正在进行中，确定要退出吗？',
                                         QMessageBox.Yes | QMessageBox.No,
                                         QMessageBox.No)
            if reply == QMessageBox.Yes:
                if self.download_thread and self.download_thread.isRunning():
                    self.download_thread.cancel()
                    self.download_thread.wait(2000)  # 等待2秒让线程安全退出
                QApplication.quit()
        else:
            QApplication.quit()

    def closeEvent(self, event: QCloseEvent):
        """重写关闭事件"""
        if self.is_downloading:
            reply = QMessageBox.question(self, '确认退出',
                                         '下载正在进行中，确定要退出吗？',
                                         QMessageBox.Yes | QMessageBox.No,
                                         QMessageBox.No)
            if reply == QMessageBox.Yes:
                if self.download_thread and self.download_thread.isRunning():
                    self.download_thread.cancel()
                    self.download_thread.wait(2000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    """主函数，确保程序正确退出"""
    try:
        app = QApplication(sys.argv)

        # 设置应用样式
        app.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QLabel {
                color: #333;
            }
        """)

        window = YouTubeDownloader()
        window.show()

        # 确保程序正确退出
        result = app.exec_()
        sys.exit(result)

    except Exception as e:
        #具体问题的报错
        logging.error(f"程序运行出错: {e}")
        sys.exit(1)


if __name__ == '__main__':

    main()
