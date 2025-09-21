# -*- coding: utf-8 -*-
import re
import threading
import concurrent.futures as futures
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk  # Treeview için

import requests
import pandas as pd
from bs4 import BeautifulSoup

# ttkbootstrap = modern tema
from ttkbootstrap import Style
from ttkbootstrap.constants import *
from ttkbootstrap.widgets import Frame, Button, Entry, Label, Progressbar


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 15


def clean(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_title_desc(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    # Title: og:title -> twitter:title -> <title> -> <h1>
    title = ""
    for m in [
        soup.find("meta", property="og:title"),
        soup.find("meta", attrs={"name": "twitter:title"}),
    ]:
        if m and m.get("content"):
            title = clean(m["content"])
            break
    if not title and soup.title:
        title = clean(soup.title.get_text())
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = clean(h1.get_text())

    # Description: description -> og:description -> twitter:description
    desc = ""
    for m in [
        soup.find("meta", attrs={"name": "description"}),
        soup.find("meta", property="og:description"),
        soup.find("meta", attrs={"name": "twitter:description"}),
    ]:
        if m and m.get("content"):
            desc = clean(m["content"])
            break

    return title, desc


def fetch(url: str) -> dict:
    try:
        # http/https otomatik dene
        tries = []
        if url.startswith("http://"):
            tries = [url.replace("http://", "https://", 1), url]
        elif url.startswith("https://"):
            tries = [url, url.replace("https://", "http://", 1)]
        else:
            tries = [f"https://{url}", f"http://{url}"]

        last_exc = None
        for candidate in tries:
            try:
                r = requests.get(candidate, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
                if r.ok and r.text:
                    title, desc = extract_title_desc(r.text)
                    return {"url": candidate, "status": r.status_code, "title": title, "description": desc}
            except Exception as e:
                last_exc = e
                continue

        # Hepsi patladıysa:
        err = last_exc.__class__.__name__ if last_exc else "ERR"
        return {"url": url, "status": err, "title": "", "description": ""}

    except Exception as e:
        return {"url": url, "status": f"ERR:{e}", "title": "", "description": ""}


class App:
    def __init__(self, root):
        # --- METRO DARK TEMA ---
        # Koyu tema: cyborg (alternatif: superhero, darkly)
        self.style = Style(theme="cyborg")
        self.root = root
        self.root.title("EBS Link Başlık & Açıklama Toplayıcı")
        self.root.geometry("1100x720")
        self.root.minsize(960, 620)

        # Metro benzeri düz/daraltılmış görünümler
        self._configure_metro_style()

        self.results = []
        self.scrape_thread = None
        self.is_scraping = False
        self.output_path = tk.StringVar(value=str(Path.cwd() / "scraped_links.xlsx"))

        self._build_ui_grid()  # responsive grid
        self._bind_window_resize()

    # --------- STYLE ----------
    def _configure_metro_style(self):
        # Varsayılan fontları bir tık büyüt (okunabilirlik)
        try:
            default_font = self.style.master.nametowidget("TkDefaultFont")
            default_font.configure(size=10)
        except Exception:
            pass

        # Düz buton hissi
        self.style.configure("TButton", relief="flat", borderwidth=0, padding=(14, 8))
        self.style.map("TButton", relief=[("pressed", "flat"), ("active", "flat")])

        # Label minimal
        self.style.configure("TLabel", padding=(2, 2))

        # Entry düz kenar
        self.style.configure("TEntry", padding=8)

        # Progressbar ince şerit
        self.style.configure("TProgressbar", thickness=6)

        # Treeview Metro: koyu arka plan, belirgin seçim rengi
        self.style.configure(
            "Metro.Treeview",
            background="#1d1f21",  # koyu grid
            fieldbackground="#1d1f21",
            foreground="#e0e0e0",
            rowheight=28,
            borderwidth=0,
        )
        self.style.configure(
            "Metro.Treeview.Heading",
            background="#2a2d2f",
            foreground="#e8e8e8",
            relief="flat",
            borderwidth=0,
            padding=(8, 6)
        )
        self.style.map(
            "Metro.Treeview",
            background=[("selected", "#0d6efd")],  # PRIMARY
            foreground=[("selected", "#ffffff")],
        )
        self.style.map(
            "Metro.Treeview.Heading",
            background=[("active", "#31363a")]
        )

    # --------- UI (GRID) ----------
    def _build_ui_grid(self):
        # Ana konteyner
        container = Frame(self.root, padding=16)
        container.grid(row=0, column=0, sticky="nsew")

        # Grid ağırlıkları (responsive)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(3, weight=1)       # tablo bölümü genişlesin
        container.grid_columnconfigure(0, weight=1)

        # Başlık
        header = Frame(container, padding=(0, 0, 0, 10))
        header.grid(row=0, column=0, sticky="ew")
        Label(header, text="URL Listesi (her satıra bir URL)", bootstyle=SECONDARY).grid(row=0, column=0, sticky="w")

        # URL Text
        text_frame = Frame(container)
        text_frame.grid(row=1, column=0, sticky="nsew", pady=(4, 8))
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        self.txt = tk.Text(text_frame, height=7, wrap="word", bg="#1b1d1f", fg="#e6e6e6", insertbackground="#ffffff", relief="flat")
        self.txt.grid(row=0, column=0, sticky="nsew")

        txt_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.txt.yview)
        self.txt.configure(yscrollcommand=txt_scroll.set)
        txt_scroll.grid(row=0, column=1, sticky="ns")

        Button(text_frame, text="Örnek URL ekle", bootstyle=LINK, command=self.fill_example).grid(row=1, column=0, sticky="w", pady=(6, 0))

        # Çıkış dosyası
        out_row = Frame(container)
        out_row.grid(row=2, column=0, sticky="ew", pady=(4, 8))
        out_row.grid_columnconfigure(1, weight=1)
        Label(out_row, text="Excel Çıkışı:", bootstyle=SECONDARY).grid(row=0, column=0, sticky="w")
        Entry(out_row, textvariable=self.output_path).grid(row=0, column=1, sticky="ew", padx=8)
        Button(out_row, text="Kaydet Yeri...", bootstyle=SECONDARY, command=self.choose_output).grid(row=0, column=2)

        # Aksiyonlar + Progress
        actions = Frame(container)
        actions.grid(row=3, column=0, sticky="ew")
        actions.grid_columnconfigure(4, weight=1)  # progress sağa yaslansın

        Button(actions, text="Tarama Başlat", bootstyle=SUCCESS, command=self.start_scrape).grid(row=0, column=0, padx=(0, 8))
        Button(actions, text="Temizle", bootstyle=WARNING, command=self.clear_all).grid(row=0, column=1, padx=(0, 8))
        Button(actions, text="Excel'e Aktar", bootstyle=INFO, command=self.export_excel).grid(row=0, column=2, padx=(0, 8))

        self.pb = Progressbar(actions, mode="indeterminate", bootstyle=INFO, length=220)
        self.pb.grid(row=0, column=4, sticky="e")

        # Sonuç Tablosu
        table_frame = Frame(container, padding=(0, 10, 0, 0))
        table_frame.grid(row=4, column=0, sticky="nsew")
        table_frame.grid_rowconfigure(1, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        Label(table_frame, text="Sonuçlar", bootstyle=SECONDARY).grid(row=0, column=0, sticky="w", pady=(0, 6))

        columns = ("url", "status", "title", "description")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=12, style="Metro.Treeview")
        for col in columns:
            self.tree.heading(col, text=col.capitalize())
        # Başlangıç genişliklerini oransal ayarlayacağız (resize event ile)
        self.tree.column("url", width=350, anchor="w")
        self.tree.column("status", width=90, anchor="w")
        self.tree.column("title", width=320, anchor="w")
        self.tree.column("description", width=520, anchor="w")

        self.tree.grid(row=1, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=yscroll.set)
        yscroll.grid(row=1, column=1, sticky="ns")

    # --------- Responsive davranış ----------
    def _bind_window_resize(self):
        # Pencere genişleyince kolonları oransal güncelle
        self.root.bind("<Configure>", self._on_resize)

    def _on_resize(self, event):
        try:
            # Toplam genişlikten scrollbar/padding düş
            tv_width = self.tree.winfo_width()
            if tv_width <= 0:
                return
            # Oranlar (toplam 1.0): url=0.30, status=0.10, title=0.27, description=0.33
            self.tree.column("url", width=int(tv_width * 0.30))
            self.tree.column("status", width=int(tv_width * 0.10))
            self.tree.column("title", width=int(tv_width * 0.27))
            self.tree.column("description", width=int(tv_width * 0.33))
        except Exception:
            pass

    # --- UI Callbacks ---
    def fill_example(self):
        ex = (
            "https://beykozunsesi.com.tr/izmir-buyuksehir-belediye-baskani-cemil-tugay-u20-zirvesinde-kimsenin-sofrada-geride-kalmamasi-icin-yerel-yoenetimler-oencu-olmali\n"
            "https://example.com\n"
        )
        self.txt.insert("1.0", ex)

    def choose_output(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile="scraped_links.xlsx",
            title="Excel çıktısı kaydet"
        )
        if path:
            self.output_path.set(path)

    def clear_all(self):
        if self.is_scraping:
            messagebox.showwarning("Uyarı", "İşlem devam ederken temizlenemez.")
            return
        self.txt.delete("1.0", tk.END)
        self.results = []
        for i in self.tree.get_children():
            self.tree.delete(i)

    def start_scrape(self):
        if self.is_scraping:
            return
        urls = [u.strip() for u in self.txt.get("1.0", tk.END).splitlines() if u.strip()]
        if not urls:
            messagebox.showinfo("Bilgi", "Lütfen en az bir URL giriniz.")
            return

        for i in self.tree.get_children():
            self.tree.delete(i)
        self.results = []

        self.is_scraping = True
        self.pb.start(10)
        self.scrape_thread = threading.Thread(target=self._scrape_worker, args=(urls,), daemon=True)
        self.scrape_thread.start()

    def _scrape_worker(self, urls: list[str]):
        try:
            rows = []
            with futures.ThreadPoolExecutor(max_workers=min(16, len(urls) or 1)) as ex:
                for res in ex.map(fetch, urls):
                    rows.append(res)
                    self.root.after(0, self._append_row_to_table, res)
            self.results = rows
        finally:
            self.root.after(0, self._end_progress)

    def _append_row_to_table(self, res: dict):
        self.tree.insert("", tk.END, values=(res["url"], res["status"], res["title"], res["description"]))

    def _end_progress(self):
        self.pb.stop()
        self.is_scraping = False
        messagebox.showinfo("Tamam", "Tarama tamamlandı.")

    def export_excel(self):
        if not self.results:
            messagebox.showinfo("Bilgi", "Sonuç yok. Önce taramayı çalıştırın.")
            return
        try:
            df = pd.DataFrame(self.results, columns=["url", "status", "title", "description"])
            out = Path(self.output_path.get())
            out.parent.mkdir(parents=True, exist_ok=True)
            df.to_excel(out, index=False)
            messagebox.showinfo("Başarılı", f"Excel kaydedildi:\n{out}")
        except Exception as e:
            messagebox.showerror("Hata", f"Excel yazarken hata: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
