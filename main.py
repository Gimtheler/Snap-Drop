import sys, os, subprocess, json, datetime, ctypes, threading
from pathlib import Path

def _pip(*p):
    for x in p:
        subprocess.call([sys.executable,"-m","pip","install",x,"-q"],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

try:
    from PIL import Image, ImageGrab, ImageTk
    from pynput import keyboard as pynkb
    import pystray
    from pystray import MenuItem, Menu
except ImportError:
    _pip("pillow","pynput","pystray")
    from PIL import Image, ImageGrab, ImageTk
    from pynput import keyboard as pynkb
    import pystray
    from pystray import MenuItem, Menu

import tkinter as tk
import winreg

BASE  = Path(__file__).parent
SHOTS = BASE/"screenshots"
CFG   = BASE/"config.json"
SHOTS.mkdir(exist_ok=True)

D = {
    "keybind":"<ctrl>+<shift>+s",
    "keybind_label":"Ctrl+Shift+S",
    "save_local":True,
    "mode":"rectangle",
    "startup":False,
    "toast_duration":0.5,
}

def load():
    if CFG.exists():
        try:
            d=json.loads(CFG.read_text())
            for k,v in D.items(): d.setdefault(k,v)
            return d
        except: pass
    return D.copy()

def save(d): CFG.write_text(json.dumps(d,indent=2))

def set_startup(on):
    exe=f'"{sys.executable}" "{Path(__file__).resolve()}"'
    try:
        k=winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows\CurrentVersion\Run",
                         0,winreg.KEY_SET_VALUE)
        if on: winreg.SetValueEx(k,"snapdrop",0,winreg.REG_SZ,exe)
        else:
            try: winreg.DeleteValue(k,"snapdrop")
            except FileNotFoundError: pass
        winreg.CloseKey(k)
    except Exception as e: print("startup:",e)

def copy_img(img):
    try:
        from io import BytesIO; import win32clipboard
        b=BytesIO(); img.convert("RGB").save(b,"BMP")
        d=b.getvalue()[14:]; b.close()
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB,d)
        win32clipboard.CloseClipboard()
    except Exception as e: print("clip:",e)

if sys.platform=="win32":
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(),0)


class Toast(tk.Toplevel):
    def __init__(self,root,msg,sub,cb,ms):
        super().__init__(root)
        self._cb=cb
        self.overrideredirect(True)
        self.attributes("-topmost",True,"-alpha",0.0)
        self.configure(bg="#1e1e1e")
        sw,sh=self.winfo_screenwidth(),self.winfo_screenheight()
        w,h=280,64
        self.geometry(f"{w}x{h}+{sw-w-16}+{sh-h-48}")
        o=tk.Frame(self,bg="#7c6bff",padx=1,pady=1); o.pack(fill="both",expand=True)
        i=tk.Frame(o,bg="#1e1e1e",padx=12,pady=8); i.pack(fill="both",expand=True)
        tk.Label(i,text=msg,bg="#1e1e1e",fg="#fff",font=("Segoe UI",9,"bold"),anchor="w").pack(fill="x")
        tk.Label(i,text=sub,bg="#1e1e1e",fg="#555",font=("Segoe UI",8),anchor="w").pack(fill="x")
        self._bind(self)
        self._fin(); self.after(ms,self._fout)

    def _bind(self,w):
        w.bind("<Button-1>",self._click)
        for c in w.winfo_children(): self._bind(c)

    def _click(self,e=None):
        self.destroy()
        if self._cb: self._cb()

    def _fin(self,a=0.0):
        if a>=1.0: return
        a=min(a+0.1,1.0); self.attributes("-alpha",a)
        self.after(20,lambda:self._fin(a))

    def _fout(self,a=1.0):
        if a<=0.0:
            try: self.destroy()
            except: pass
            return
        a=max(a-0.1,0.0)
        try: self.attributes("-alpha",a); self.after(20,lambda:self._fout(a))
        except: pass


class Overlay(tk.Toplevel):
    def __init__(self,root,cb):
        super().__init__(root)
        self._cb=cb; self.sx=self.sy=0; self.r=None
        self.attributes("-fullscreen",True,"-alpha",0.25,"-topmost",True)
        self.configure(bg="black",cursor="crosshair"); self.overrideredirect(True)
        cv=tk.Canvas(self,bg="black",highlightthickness=0); cv.pack(fill="both",expand=True)
        cv.create_text(self.winfo_screenwidth()//2,34,
                       text="drag to snip   •   esc to cancel",
                       fill="#fff",font=("Segoe UI",12))
        cv.bind("<ButtonPress-1>",self._p)
        cv.bind("<B1-Motion>",self._d)
        cv.bind("<ButtonRelease-1>",self._r)
        self.bind("<Escape>",lambda e:self._cancel())
        self._cv=cv

    def _p(self,e):
        self.sx,self.sy=e.x,e.y
        self.r=self._cv.create_rectangle(e.x,e.y,e.x,e.y,
                                          outline="#7c6bff",width=2,
                                          fill="#7c6bff",stipple="gray25")
    def _d(self,e):
        if self.r: self._cv.coords(self.r,self.sx,self.sy,e.x,e.y)

    def _r(self,e):
        x1,y1=min(self.sx,e.x),min(self.sy,e.y)
        x2,y2=max(self.sx,e.x),max(self.sy,e.y)
        self.destroy()
        self._cb(None,None,None,None) if (x2-x1<4 or y2-y1<4) else self._cb(x1,y1,x2,y2)

    def _cancel(self): self.destroy(); self._cb(None,None,None,None)


class Preview(tk.Toplevel):
    def __init__(self,root,img,path):
        super().__init__(root)
        self.title("snapdrop"); self.configure(bg="#111")
        self.resizable(False,False); self.attributes("-topmost",True)
        t=img.copy(); t.thumbnail((520,340))
        self._i=ImageTk.PhotoImage(t)
        tk.Label(self,image=self._i,bg="#111").pack(padx=12,pady=(12,6))
        bar=tk.Frame(self,bg="#1a1a1a"); bar.pack(fill="x",padx=12,pady=4)
        tk.Label(bar,text=f"✓  {path.name}  — copied",bg="#1a1a1a",fg="#22c55e",
                 font=("Segoe UI",9)).pack(side="left",padx=8,pady=8)
        f=tk.Frame(self,bg="#111"); f.pack(fill="x",padx=12,pady=(0,12))
        tk.Button(f,text="open folder",bg="#1e1e1e",fg="#888",relief="flat",
                  font=("Segoe UI",9),
                  command=lambda:os.startfile(str(path.parent))).pack(side="left")
        tk.Button(f,text="close",bg="#1e1e1e",fg="#888",relief="flat",
                  font=("Segoe UI",9),command=self.destroy).pack(side="right")


class Settings(tk.Toplevel):
    def __init__(self,root,cfg,on_save):
        super().__init__(root)
        self.title("settings"); self.configure(bg="#111")
        self.resizable(False,False); self.attributes("-topmost",True)
        self.cfg=cfg.copy(); self.on_save=on_save
        self._keys=set(); self._rec=False

        def lbl(t): tk.Label(self,text=t,bg="#111",fg="#555",font=("Segoe UI",8)).pack(anchor="w",padx=16,pady=(10,2))
        def sep(): tk.Frame(self,bg="#222",height=1).pack(fill="x",padx=16,pady=4)

        tk.Label(self,text="settings",bg="#111",fg="#f0f0f0",
                 font=("Segoe UI",13,"bold")).pack(anchor="w",padx=16,pady=(14,4))
        sep()

        lbl("keybind")
        kf=tk.Frame(self,bg="#111"); kf.pack(fill="x",padx=16,pady=(0,6))
        self.kb=tk.StringVar(value=cfg["keybind_label"])
        tk.Entry(kf,textvariable=self.kb,bg="#1a1a1a",fg="#a78bfa",relief="flat",
                 font=("Consolas",10),state="readonly",readonlybackground="#1a1a1a",
                 width=20).pack(side="left",ipady=5,padx=(0,8))
        self.rb=tk.Button(kf,text="record",bg="#7c6bff",fg="white",relief="flat",
                          font=("Segoe UI",9,"bold"),padx=8,command=self._rec_start)
        self.rb.pack(side="left")
        sep()

        lbl("toast duration")
        tf=tk.Frame(self,bg="#111"); tf.pack(fill="x",padx=16,pady=(0,8))
        self.tv=tk.DoubleVar(value=cfg.get("toast_duration",0.5))
        for v in [0.5,1.0,2.0,3.0,5.0]:
            tk.Radiobutton(tf,text=f"{v}s",variable=self.tv,value=v,
                           bg="#111",fg="#aaa",selectcolor="#1a1a2e",
                           activebackground="#111",font=("Segoe UI",9)
                           ).pack(side="left",padx=(0,10))
        sep()

        self.sv=tk.BooleanVar(value=cfg.get("save_local",True))
        tk.Checkbutton(self,text="save screenshots locally",variable=self.sv,
                       bg="#111",fg="#aaa",selectcolor="#1a1a2e",
                       activebackground="#111",font=("Segoe UI",9)
                       ).pack(anchor="w",padx=16,pady=6)

        self.stv=tk.BooleanVar(value=cfg.get("startup",False))
        tk.Checkbutton(self,text="start with windows",variable=self.stv,
                       bg="#111",fg="#aaa",selectcolor="#1a1a2e",
                       activebackground="#111",font=("Segoe UI",9)
                       ).pack(anchor="w",padx=16,pady=(0,6))
        sep()

        tk.Button(self,text="save",bg="#7c6bff",fg="white",relief="flat",
                  font=("Segoe UI",10,"bold"),padx=20,pady=8,
                  command=self._save).pack(pady=14)

    def _rec_start(self):
        self._rec=True; self._keys=set()
        self.kb.set("press keys...")
        self.rb.configure(text="listening...",bg="#444")
        self.bind("<KeyPress>",self._kp); self.bind("<KeyRelease>",self._kr)
        self.focus_set()

    def _kp(self,e):
        if self._rec: self._keys.add(e.keysym); self.kb.set("+".join(sorted(self._keys)))

    def _kr(self,e):
        if not self._rec: return
        self._rec=False
        mods={"Control_L":"<ctrl>","Control_R":"<ctrl>",
              "Shift_L":"<shift>","Shift_R":"<shift>",
              "Alt_L":"<alt>","Alt_R":"<alt>",
              "Super_L":"<cmd>","Super_R":"<cmd>",
              "Win_L":"<cmd>","Win_R":"<cmd>"}
        parts,labels=[],[]
        for k in sorted(self._keys):
            if k in mods and mods[k] not in parts:
                parts.append(mods[k]); labels.append(k.split("_")[0].capitalize())
        for k in sorted(self._keys):
            if k not in mods:
                parts.append(k.lower())
                labels.append(k.upper() if len(k)==1 else k.capitalize())
        self.cfg["keybind"]="+"  .join(parts)
        self.cfg["keybind_label"]="+".join(labels)
        self.kb.set(self.cfg["keybind_label"])
        self.rb.configure(text="record",bg="#7c6bff")
        self.unbind("<KeyPress>"); self.unbind("<KeyRelease>")

    def _save(self):
        self.cfg["save_local"]=self.sv.get()
        self.cfg["startup"]=self.stv.get()
        self.cfg["toast_duration"]=self.tv.get()
        self.on_save(self.cfg); self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg=load()
        self._busy=False; self._listener=None
        self._img=None; self._path=None

        self.title("snapdrop"); self.configure(bg="#0f0f0f")
        self.resizable(False,False)
        self.protocol("WM_DELETE_WINDOW",self._tray)

        self._build(); self._mk_tray(); self._hotkey()

        self.update_idletasks()
        w,h=360,440
        self.geometry(f"{w}x{h}+{(self.winfo_screenwidth()-w)//2}+{(self.winfo_screenheight()-h)//2}")
        if self.cfg.get("startup"): self.after(100,self.withdraw)

    def _mk_tray(self):
        ico=Image.new("RGB",(64,64),"#7c6bff")
        self._tray=pystray.Icon("snapdrop",ico,"snapdrop",Menu(
            MenuItem("open",      self._show, default=True),
            MenuItem("capture",   lambda i,it: self.after(0,self.capture)),
            Menu.SEPARATOR,
            MenuItem("exit",      lambda i,it: self.after(0,self._exit)),
        ))
        threading.Thread(target=self._tray.run,daemon=True).start()

    def _tray(self):   self.withdraw()
    def _show(self,*_): self.after(0,lambda:[self.deiconify(),self.lift(),self.focus_force()])
    def _exit(self):
        try: self._tray.stop()
        except: pass
        self.destroy()

    def _build(self):
        hdr=tk.Frame(self,bg="#0f0f0f"); hdr.pack(fill="x",padx=16,pady=(16,4))
        tk.Label(hdr,text="snapdrop",bg="#0f0f0f",fg="#fff",
                 font=("Segoe UI",15,"bold")).pack(side="left")
        tk.Button(hdr,text="⚙",bg="#0f0f0f",fg="#444",relief="flat",
                  font=("Segoe UI",12),activebackground="#0f0f0f",activeforeground="#aaa",
                  command=self._settings).pack(side="right")

        tk.Frame(self,bg="#1e1e1e",height=1).pack(fill="x",padx=16,pady=(2,10))
        tk.Label(self,text="MODE",bg="#0f0f0f",fg="#333",
                 font=("Segoe UI",7,"bold")).pack(anchor="w",padx=16)

        self.mode=tk.StringVar(value=self.cfg.get("mode","rectangle"))
        mf=tk.Frame(self,bg="#0f0f0f"); mf.pack(fill="x",padx=16,pady=(4,12))
        for val,lbl in [("rectangle","✂  rect"),("fullscreen","⛶  full"),
                         ("window","🗔  window"),("timer","⏱  timer")]:
            tk.Radiobutton(mf,text=lbl,variable=self.mode,value=val,
                           indicatoron=False,bg="#181818",fg="#777",
                           selectcolor="#7c6bff",activebackground="#222",activeforeground="#fff",
                           relief="flat",font=("Segoe UI",9),padx=10,pady=7,
                           cursor="hand2",bd=0).pack(side="left",padx=(0,3))

        tr=tk.Frame(self,bg="#0f0f0f"); tr.pack(fill="x",padx=16,pady=(0,10))
        tk.Label(tr,text="delay:",bg="#0f0f0f",fg="#333",font=("Segoe UI",8)).pack(side="left",padx=(0,6))
        self.td=tk.IntVar(value=0)
        for v in [0,1,2,3,5,10]:
            tk.Radiobutton(tr,text="instant" if v==0 else f"{v}s",variable=self.td,value=v,
                           bg="#0f0f0f",fg="#444",selectcolor="#1a1a2e",
                           activebackground="#0f0f0f",font=("Segoe UI",8)
                           ).pack(side="left",padx=(0,5))

        tk.Frame(self,bg="#1e1e1e",height=1).pack(fill="x",padx=16,pady=(0,10))

        self.btn=tk.Button(self,text="capture",bg="#7c6bff",fg="#fff",relief="flat",
                           font=("Segoe UI",13,"bold"),pady=13,
                           activebackground="#9585ff",activeforeground="#fff",
                           cursor="hand2",command=self.capture)
        self.btn.pack(fill="x",padx=16)

        self.kl=tk.Label(self,text=f"hotkey: {self.cfg['keybind_label']}",
                         bg="#0f0f0f",fg="#2e2e2e",font=("Segoe UI",8))
        self.kl.pack(pady=(5,2))
        tk.Label(self,text="✕ minimises to tray",bg="#0f0f0f",fg="#222",
                 font=("Segoe UI",7)).pack(pady=(0,10))

        tk.Frame(self,bg="#1e1e1e",height=1).pack(fill="x",padx=16,pady=(0,8))

        self.st=tk.StringVar(value="ready")
        tk.Label(self,textvariable=self.st,bg="#0f0f0f",fg="#3a3a3a",
                 font=("Consolas",8)).pack(anchor="w",padx=16)

        tk.Label(self,text="RECENT",bg="#0f0f0f",fg="#292929",
                 font=("Segoe UI",7,"bold")).pack(anchor="w",padx=16,pady=(10,3))

        self.lb=tk.Listbox(self,bg="#0a0a0a",fg="#444",relief="flat",
                           selectbackground="#7c6bff",selectforeground="#fff",
                           font=("Consolas",8),activestyle="none",
                           borderwidth=0,highlightthickness=0,height=6)
        self.lb.pack(fill="both",expand=True,padx=16,pady=(0,16))
        self.lb.bind("<Double-Button-1>",self._open)
        self._refresh()

    def _refresh(self):
        self.lb.delete(0,"end")
        shots=sorted(SHOTS.glob("*.png"),reverse=True)[:10]
        for s in shots: self.lb.insert("end",f"  {s.name}")
        if not shots: self.lb.insert("end","  no screenshots yet")

    def _open(self,e):
        sel=self.lb.curselection()
        if sel:
            p=SHOTS/self.lb.get(sel[0]).strip()
            if p.exists(): os.startfile(str(p))

    def _settings(self):
        def _s(c):
            self.cfg=c; save(c); set_startup(c.get("startup",False))
            self.kl.configure(text=f"hotkey: {c['keybind_label']}")
            self._hotkey()
        Settings(self,self.cfg,_s)

    def _hotkey(self):
        if self._listener:
            try: self._listener.stop()
            except: pass
            self._listener=None
        try:
            self._listener=pynkb.GlobalHotKeys({self.cfg["keybind"]:lambda:self.after(0,self.capture)})
            self._listener.daemon=True; self._listener.start()
        except Exception as e: print("hotkey err:",e)

    def capture(self):
        if self._busy: return
        self._busy=True; self.btn.configure(state="disabled")
        m=self.mode.get(); self.cfg["mode"]=m; save(self.cfg)
        if   m=="rectangle":  self._rect()
        elif m=="fullscreen": self._full()
        elif m=="window":     self._win()
        elif m=="timer":
            d=self.td.get()
            self._full() if d==0 else self._timer(d)

    def _unlock(self): self._busy=False; self.btn.configure(state="normal")

    def _rect(self):
        v=self.state()!="withdrawn"
        if v: self.withdraw()
        self.after(150,lambda:Overlay(self,lambda *a:self._rect_done(v,*a)).focus_set())

    def _rect_done(self,v,x1,y1,x2,y2):
        if v: self.deiconify()
        self._unlock()
        if x1 is None: self.st.set("cancelled"); return
        self.after(50,lambda:self._process(ImageGrab.grab(bbox=(x1,y1,x2,y2))))

    def _full(self):
        v=self.state()!="withdrawn"
        if v: self.withdraw()
        self.after(200,lambda:self._gfull(v))

    def _gfull(self,v):
        img=ImageGrab.grab()
        if v: self.deiconify()
        self._unlock(); self._process(img)

    def _win(self):
        v=self.state()!="withdrawn"
        if v: self.withdraw()
        self.after(200,lambda:self._gwin(v))

    def _gwin(self,v):
        try:
            import win32gui
            img=ImageGrab.grab(bbox=win32gui.GetWindowRect(win32gui.GetForegroundWindow()))
        except: img=ImageGrab.grab()
        if v: self.deiconify()
        self._unlock(); self._process(img)

    def _timer(self,n):
        self.st.set(f"capturing in {n}...")
        if n<=0: self._full()
        else: self.after(1000,lambda:self._timer(n-1))

    def _process(self,img):
        ts=datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        p=SHOTS/f"snap_{ts}.png"
        if self.cfg.get("save_local",True): img.save(p)
        copy_img(img)
        self._img=img; self._path=p
        self.st.set(f"copied  •  {p.name}"); self._refresh()
        ms=int(self.cfg.get("toast_duration",0.5)*1000)
        Toast(self,"screenshot taken","click to view",
              lambda:Preview(self,self._img,self._path),ms)


if __name__=="__main__":
    App().mainloop()
