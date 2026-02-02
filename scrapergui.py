import asyncio
from playwright.async_api import async_playwright
import os
import re
import httpx
import random
import customtkinter as ctk
import tkinter.messagebox as messagebox
import threading
import sys

# -----------------------------------------------------
# Playwright 和 httpx 的异步爬取逻辑
# -----------------------------------------------------

# 下载函数（使用用户自定义的代理端口）
async def download_img(url, path, proxy_url):
    try:
        async with httpx.AsyncClient(proxy=proxy_url, verify=False) as client: # verify=False 应对某些代理SSL问题
            # 增加 headers 模拟浏览器下载图片，防止 403
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            resp = await client.get(url, timeout=20, follow_redirects=True, headers=headers)
            if resp.status_code == 200:
                with open(path, 'wb') as f:
                    f.write(resp.content)
                return True
            else:
                print(f"下载失败，状态码: {resp.status_code} - {url}")
        return False
    except Exception as e:
        print(f"下载异常: {url}，原因: {e}")
        return False

# Playwright 核心爬虫逻辑
async def run_scraper_core(keyword, max_pages, proxy_port, update_callback):
    proxy_url = f"http://127.0.0.1:{proxy_port}"

    # 自动检测本地 Chrome 或 Edge 路径
    chrome_path = None
    if sys.platform == "win32":
        default_chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if os.path.exists(default_chrome_path):
            chrome_path = default_chrome_path
        else:
            default_edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            if os.path.exists(default_edge_path):
                chrome_path = default_edge_path
                update_callback("未找到 Chrome，已自动切换至 Edge 浏览器。")
    
    if not chrome_path:
        update_callback("错误：未检测到本地 Chrome 或 Edge 浏览器，Playwright 将尝试启动自带浏览器。")
        # 如果依然无法启动，用户可能需要手动安装 playwight install chromium
        # 否则 Playwright 可能会报错
        executable_arg = {}
    else:
        executable_arg = {"executable_path": chrome_path}
        update_callback(f"正在尝试调用本地浏览器: {chrome_path}")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=False, # 设置为 False，这样你能看到浏览器操作，方便过验证码
                proxy={"server": proxy_url},
                args=["--disable-blink-features=AutomationControlled", "--mute-audio", "--no-sandbox"],
                **executable_arg # 传入 executable_path (如果有的话)
            )
        except Exception as e:
            update_callback(f"错误：浏览器启动失败！请确保代理 {proxy_url} 可用，或尝试 `playwright install chromium`。详细: {e}")
            return

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080} # 设置固定的分辨率
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = await context.new_page()

        # 创建主关键词文件夹
        main_folder = os.path.join(os.getcwd(), keyword.replace(' ', '_')) # 将空格替换为下划线，作为文件夹名

        if not os.path.exists(keyword):
            os.makedirs(keyword)

        for p_num in range(1, max_pages + 1):
            update_callback(f"--- 正在处理第 {p_num} 页 ---")
            url = f"https://www.etsy.com/sg-en/search?q={keyword}&ref=pagination&as_prefix&page={p_num}"
            
            await page.goto(url, wait_until="domcontentloaded")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(5) 

            # 1. 获取详情页链接 (增强版)
            hrefs = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a'))
                        .map(a => a.href)
                        .filter(href => href.includes('/listing/'))
            """)
            detail_urls = list(set([h.split('?')[0] for h in hrefs]))
            update_callback(f"发现 {len(detail_urls)} 个商品详情页")

            # 2. 遍历详情页 (使用你跑通的逻辑)
            for idx, d_url in enumerate(detail_urls):
                try:
                    # 提取 Listing ID 并创建子文件夹
                    listing_id = d_url.split('/listing/')[1].split('/')[0]
                    item_folder = os.path.join(keyword, listing_id)
                    if not os.path.exists(item_folder):
                        os.makedirs(item_folder)

                    update_callback(f"[{idx+1}/{len(detail_urls)}] 进入详情页: {listing_id}")
                    
                    # 访问详情页
                    await page.goto(d_url, wait_until="domcontentloaded")
                    await asyncio.sleep(random.uniform(2, 4)) # 模拟人类停留

                    # --- 核心修改：使用你提供的选择器 ---
                    img_elements = await page.query_selector_all('.image-carousel-container img, ul.carousel-pane-list img')
                    
                    current_item_imgs = []
                    for img in img_elements:
                        # 尝试获取 src
                        src = await img.get_attribute('data-src') or await img.get_attribute('src')
                        if src:
                            # 强行转换高清格式 (fullxfull)
                            full_url = re.sub(r'_\d+x\d+', '_fullxfull', src)
                            current_item_imgs.append(full_url)
                    
                    # 转换后去重，防止下载重复的高清原图
                    current_item_imgs = list(set(current_item_imgs))
                    update_callback(f"  找到 {len(current_item_imgs)} 张高清图")

                    for i, img_url in enumerate(current_item_imgs):
                        file_path = os.path.join(item_folder, f"image_{i}.jpg")
                        # 调用带代理端口的下载函数
                        if await download_img(img_url, file_path, proxy_url):
                            update_callback(f"    已保存: {file_path}")
                        await asyncio.sleep(0.3) 

                except Exception as e:
                    update_callback(f"商品 {d_url} 处理失败: {e}")
                    continue

        await browser.close()
        update_callback("所有任务已完成！")

# -----------------------------------------------------
# GUI 界面逻辑
# -----------------------------------------------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Etsy 高清图片采集器")
        self.geometry("600x650")  # 稍微增加初始高度
        self.grid_columnconfigure(0, weight=1)
        
        # 关键词输入 (Row 0, 1)
        self.keyword_label = ctk.CTkLabel(self, text="搜索关键词:")
        self.keyword_label.grid(row=0, column=0, padx=20, pady=(15, 0), sticky="w")
        self.keyword_entry = ctk.CTkEntry(self, placeholder_text="例如: abstract oil painting")
        self.keyword_entry.grid(row=1, column=0, padx=20, pady=5, sticky="ew")

        # 爬取页数输入 (Row 2, 3)
        self.pages_label = ctk.CTkLabel(self, text="爬取页数 (1-20):")
        self.pages_label.grid(row=2, column=0, padx=20, pady=(10, 0), sticky="w")
        self.pages_entry = ctk.CTkEntry(self, placeholder_text="例如: 3")
        self.pages_entry.grid(row=3, column=0, padx=20, pady=5, sticky="ew")
        self.pages_entry.insert(0, "1")

        # 代理端口输入 (Row 4, 5) - 这里之前可能跟后面的 Row 冲突了
        self.proxy_label = ctk.CTkLabel(self, text="本地代理端口 (例如 10808):")
        self.proxy_label.grid(row=4, column=0, padx=20, pady=(10, 0), sticky="w")
        self.proxy_entry = ctk.CTkEntry(self, placeholder_text="10808")
        self.proxy_entry.grid(row=5, column=0, padx=20, pady=5, sticky="ew")
        self.proxy_entry.insert(0, "10808")

        # 开始按钮 (Row 6)
        self.start_button = ctk.CTkButton(self, text="开始运行", command=self.start_scraper_thread, fg_color="#F1641E", hover_color="#D55719") # Etsy 橙色
        self.start_button.grid(row=6, column=0, padx=20, pady=20, sticky="ew")

        # 日志区域 (Row 7, 8)
        self.log_label = ctk.CTkLabel(self, text="运行状态日志:")
        self.log_label.grid(row=7, column=0, padx=20, pady=0, sticky="w")
        self.log_textbox = ctk.CTkTextbox(self, height=200) # 增加高度
        self.log_textbox.grid(row=8, column=0, padx=20, pady=(5, 20), sticky="nsew")
        
        # 设置权重，让日志框 (Row 8) 随窗口缩放
        self.grid_rowconfigure(8, weight=1)
        self.log_textbox.configure(state="disabled")
    def update_log(self, message):
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", message + "\n")
        self.log_textbox.see("end") # 自动滚动到底部
        self.log_textbox.configure(state="disabled")

    def start_scraper_thread(self):
        keyword = self.keyword_entry.get().strip()
        pages_str = self.pages_entry.get().strip()
        proxy_port_str = self.proxy_entry.get().strip()

        if not keyword:
            messagebox.showerror("输入错误", "关键词不能为空！")
            return
        
        try:
            max_pages = int(pages_str)
            if not (1 <= max_pages <= 20): # 限制页数，防止过度请求
                messagebox.showerror("输入错误", "爬取页数必须在 1 到 20 之间！")
                return
        except ValueError:
            messagebox.showerror("输入错误", "爬取页数必须是有效数字！")
            return
        
        try:
            proxy_port = int(proxy_port_str)
            if not (1024 <= proxy_port <= 65535): # 代理端口范围
                 messagebox.showerror("输入错误", "代理端口必须是 1024 到 65535 之间的有效端口号！")
                 return
        except ValueError:
            messagebox.showerror("输入错误", "代理端口必须是有效数字！")
            return

        self.update_log("-------------------- 任务开始 --------------------")
        self.start_button.configure(state="disabled", text="正在运行...")
        
        # 使用线程来运行异步爬虫，避免 GUI 卡死
        scraper_thread = threading.Thread(target=self._run_async_scraper, args=(keyword, max_pages, proxy_port))
        scraper_thread.start()

    def _run_async_scraper(self, keyword, max_pages, proxy_port):
        # 创建新的事件循环，因为线程默认没有
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_scraper_core(keyword, max_pages, proxy_port, self.update_log))
        except Exception as e:
            self.update_log(f"任务中发生未预期错误: {e}")
        finally:
            loop.close()
            self.update_log("-------------------- 任务结束 --------------------")
            self.start_button.configure(state="normal", text="开始爬取")

if __name__ == "__main__":
    app = App()
    app.mainloop()