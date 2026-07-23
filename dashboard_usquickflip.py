# -*- coding: utf-8 -*-
"""USQuickFlip -- shadow collector dashboard + background poller (port 5009).

Single process: a Flask one-pager plus a daemon thread that re-analyses ^GSPC every
5 min (Gaius Commission 011 strategy, engulfing-only) and appends to quickflip_log.csv.
SHADOW ONLY -- no broker, no Stanley/Arthur/Morgan/Lancelot, no real capital.
"""
import csv
import threading
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify

import quickflip_core as qf

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR  = BASE_DIR / "logs"
LOG_CSV  = LOG_DIR / "quickflip_log.csv"
_VER     = BASE_DIR / "VERSION"
VERSION  = _VER.read_text().strip() if _VER.exists() else "1.0.0"
PORT     = 5009
POLL_SEC = 300

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
logging.Formatter.converter = time.gmtime
log = logging.getLogger("usquickflip")

app = Flask(__name__)
_state = {"records": [], "stats": {}, "today": None, "updated_utc": "--",
          "latest_atr": None, "error": None}
_lock = threading.Lock()


def _write_csv(records):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=qf.CSV_COLUMNS)
        w.writeheader()
        for r in records:
            w.writerow({k: r.get(k, "") for k in qf.CSV_COLUMNS})


def refresh():
    try:
        now = datetime.now(timezone.utc)
        daily, five = qf.fetch()
        recs = qf.build_records(daily, five, now_utc=now)
        st = qf.stats(recs)
        today_est = None
        try:
            today_est = five.index[-1].tz_convert("America/New_York").date()
        except Exception:
            today_est = now.date()
        today = next((r for r in reversed(recs) if r["date"] == str(today_est)), None)
        with _lock:
            _state["records"] = recs
            _state["stats"] = st
            _state["today"] = today
            _state["latest_atr"] = qf.latest_atr(daily)
            _state["updated_utc"] = now.strftime("%Y-%m-%d %H:%M:%S UTC")
            _state["error"] = None
        _write_csv(recs)
        log.info("refresh ok | days=%d setups=%d win%%=%.1f pnl=GBP%.2f",
                 st.get("trading_days", 0), st.get("setups", 0),
                 st.get("win_rate", 0), st.get("total_pnl_gbp", 0))
    except Exception as exc:
        with _lock:
            _state["error"] = str(exc)
        log.warning("refresh failed: %s", exc)


def _loop():
    while True:
        refresh()
        time.sleep(POLL_SEC)


def archie_brief():
    with _lock:
        s = dict(_state["stats"]); t = _state["today"]; upd = _state["updated_utc"]
    L = []
    a = L.append
    a("=" * 52)
    a("ARCHIE BRIEF -- USQuickFlip Shadow Collector v%s" % VERSION)
    a("US500 (^GSPC) | Quick Flip Scalper | Gaius Commission 011")
    a("Generated: %s" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    a("Data updated: %s" % upd)
    a("=" * 52)
    a("")
    a("RUNNING STATISTICS (engulfing-only, GBP20 fixed risk)")
    a("  Trading days observed:  %s" % s.get("trading_days", 0))
    a("  Manipulation days:      %s (%s%% of days)" % (s.get("manip_days", 0), s.get("manip_pct", 0)))
    a("  Valid reversal setups:  %s (%s%% of manip days)" % (s.get("setups", 0), s.get("reversal_pct", 0)))
    a("  Resolved trades:        %s" % s.get("resolved", 0))
    a("  Win rate:               %s%% (%s wins)" % (s.get("win_rate", 0), s.get("wins", 0)))
    a("  Average R:R:            %s" % s.get("avg_rr", 0))
    a("  Theoretical P&L:        GBP %s" % s.get("total_pnl_gbp", 0))
    a("")
    a("TODAY")
    if t:
        a("  %s | opening range %s-%s (%s) | ATR %s | %s%% of ATR | manip=%s | %s open"
          % (t["date"], t.get("opening_low"), t.get("opening_high"), t.get("opening_range"),
             t.get("daily_atr"), t.get("atr_pct"), t.get("manip_candle"), t.get("candle_colour")))
        if t.get("reversal_found") == "YES":
            a("  Setup: %s @ %s | entry %s stop %s target %s | R:R %s | outcome=%s (%s)"
              % (t.get("reversal_type"), t.get("reversal_time"), t.get("entry_price"),
                 t.get("stop_price"), t.get("target_price"), t.get("rr_ratio"),
                 t.get("outcome"), t.get("pnl_gbp")))
        else:
            a("  Reversal: %s | outcome=%s (%s)"
              % (t.get("reversal_found"), t.get("outcome"), t.get("notes")))
    else:
        a("  (no data for today yet)")
    a("")
    a("SHADOW COLLECTOR -- no capital traded. Forward-test to confirm the")
    a("~40%% win rate before commissioning USQuickFlipTrader (Commission 011).")
    a("=" * 52)
    return "\n".join(L)


@app.route("/api/state")
def api_state():
    with _lock:
        return jsonify({
            "version": VERSION, "port": PORT,
            "stats": _state["stats"], "today": _state["today"],
            "latest_atr": _state["latest_atr"], "updated_utc": _state["updated_utc"],
            "error": _state["error"],
            "recent": list(reversed(_state["records"]))[:20],
        })


@app.route("/api/archie-brief")
def api_archie_brief():
    return archie_brief(), 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "system": "USQuickFlip",
                    "time": datetime.now(timezone.utc).isoformat()})


@app.route("/")
def index():
    return PAGE.replace("__VER__", VERSION)


PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<title>USQuickFlip A.I. -- Shadow Collector</title>
<style>
:root{--bg:#0d0f14;--bg2:#161a22;--bd:#2a3040;--tx:#e6edf3;--mut:#8b94a3;
--us:#4b8bff;--green:#3fb950;--red:#f85149;--amber:#d29922;}
*{box-sizing:border-box;}body{margin:0;background:var(--bg);color:var(--tx);
font-family:'Segoe UI',system-ui,sans-serif;font-size:13px;}
header{background:var(--bg2);border-bottom:2px solid var(--us);padding:10px 18px;
display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;}
.brand{font-size:18px;font-weight:800;color:var(--us);letter-spacing:1px;}
.brand small{color:var(--mut);font-size:11px;font-weight:400;margin-left:8px;}
.clock{font-family:monospace;color:var(--us);font-weight:700;}
.wrap{max-width:1000px;margin:0 auto;padding:18px;}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:16px;}
.card{background:var(--bg2);border:1px solid var(--bd);border-radius:10px;padding:14px 16px;}
.card h3{margin:0 0 8px;font-size:12px;letter-spacing:1px;color:var(--us);text-transform:uppercase;}
.row{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.04);}
.row .k{color:var(--mut);} .big{font-size:22px;font-weight:800;color:var(--us);}
.yes{color:var(--green);font-weight:700;} .no{color:var(--mut);} .pend{color:var(--amber);font-weight:700;}
.win{color:var(--green);font-weight:700;} .loss{color:var(--red);font-weight:700;}
.navbtn{font-size:12px;font-weight:700;color:var(--us);background:rgba(75,139,255,.12);
border:1px solid var(--us);padding:6px 12px;border-radius:6px;cursor:pointer;}
.navbtn:hover{background:rgba(75,139,255,.22);}
table{width:100%;border-collapse:collapse;font-size:11px;margin-top:6px;}
th{text-align:left;color:var(--mut);border-bottom:1px solid var(--bd);padding:6px 6px;font-weight:600;}
td{padding:5px 6px;border-bottom:1px solid rgba(255,255,255,.04);white-space:nowrap;}
.scroll{overflow-x:auto;}
.note{color:var(--mut);font-size:10px;margin-top:12px;text-align:center;line-height:1.5;}
#brief{white-space:pre;font-family:monospace;font-size:11px;background:#0a0c10;border:1px solid var(--bd);
border-radius:8px;padding:12px;margin-top:12px;display:none;color:var(--tx);}
</style></head><body>
<header>
  <div class="brand">USQUICKFLIP <small>v__VER__ &middot; port 5009 &middot; US500 shadow collector &middot; Commission 011</small></div>
  <div style="display:flex;gap:10px;align-items:center;">
    <button class="navbtn" onclick="brief()">ARCHIE BRIEF</button>
    <div class="clock" id="clk">--:--:-- UTC</div>
  </div>
</header>
<div class="wrap">
  <div class="grid">
    <div class="card"><h3>Today &mdash; <span id="tdate">--</span></h3><div id="today">Loading...</div></div>
    <div class="card"><h3>Running Statistics</h3><div id="stats">Loading...</div></div>
  </div>
  <div class="card"><h3>Log &mdash; last 20 days</h3><div class="scroll"><div id="logtbl">Loading...</div></div></div>
  <div id="brief"></div>
  <div class="note">SHADOW COLLECTOR &mdash; observes and logs theoretical setups only. No broker, no capital.
    Data via yfinance (^GSPC, ~15-min delayed). Session open keyed to the US RTH open (13:30 UTC summer / 14:30 UTC winter).</div>
</div>
<script>
function clk(){var t=new Date();document.getElementById('clk').textContent=
 String(t.getUTCHours()).padStart(2,'0')+':'+String(t.getUTCMinutes()).padStart(2,'0')+':'+String(t.getUTCSeconds()).padStart(2,'0')+' UTC';}
setInterval(clk,1000);clk();
function r(k,v,cls){return '<div class="row"><span class="k">'+k+'</span><span class="'+(cls||'')+'">'+(v==null||v===''?'--':v)+'</span></div>';}
function ocls(o){return o==='WIN'?'win':o==='LOSS'?'loss':o==='PENDING'?'pend':'no';}
function load(){
 fetch('/api/state').then(function(x){return x.json();}).then(function(d){
  var t=d.today||{};var s=d.stats||{};
  document.getElementById('tdate').textContent=t.date||'--';
  var mc=(t.manip_candle==='YES')?'<span class="yes">YES</span>':'<span class="no">NO</span>';
  var h='';
  h+=r('Opening range',(t.opening_low!=null?('$'+t.opening_low+' - $'+t.opening_high):'--'));
  h+=r('Range / Daily ATR',(t.opening_range!=null?('$'+t.opening_range+' / $'+t.daily_atr):'--'));
  h+=r('ATR %',(t.atr_pct!=null?(t.atr_pct+'%'):'--'));
  h+=r('Manipulation candle',mc);
  h+=r('Opening colour',t.candle_colour);
  h+=r('Reversal',(t.reversal_found==='YES'?'<span class="yes">'+t.reversal_type+' @ '+t.reversal_time+'</span>':'<span class="'+(t.reversal_found==='PENDING'?'pend':'no')+'">'+(t.reversal_found||'--')+'</span>'));
  if(t.reversal_found==='YES'){
    h+=r('Entry / Stop / Target','$'+t.entry_price+' / $'+t.stop_price+' / $'+t.target_price);
    h+=r('R:R',t.rr_ratio);
    h+=r('Stake (GBP20 risk)','£'+t.stake_gbp+'/pt');
  }
  h+=r('Outcome,','<span class="'+ocls(t.outcome)+'">'+(t.outcome||'--')+(t.pnl_gbp!==''&&t.pnl_gbp!=null?(' ('+(t.pnl_gbp>=0?'+':'')+'£'+t.pnl_gbp+')'):'')+'</span>');
  document.getElementById('today').innerHTML=h;
  var sh='';
  sh+='<div class="row"><span class="k">Theoretical P&amp;L</span><span class="big">'+((s.total_pnl_gbp>=0?'+£':'-£')+Math.abs(s.total_pnl_gbp||0).toFixed(2))+'</span></div>';
  sh+=r('Win rate',(s.win_rate!=null?(s.win_rate+'% ('+s.wins+'/'+s.resolved+')'):'--'));
  sh+=r('Average R:R',s.avg_rr);
  sh+=r('Setups found',s.setups);
  sh+=r('Manip days',(s.manip_days!=null?(s.manip_days+' ('+s.manip_pct+'% of '+s.trading_days+' days)'):'--'));
  sh+=r('Reversal rate',(s.reversal_pct!=null?(s.reversal_pct+'% of manip days'):'--'));
  sh+=r('Updated',d.updated_utc);
  document.getElementById('stats').innerHTML=sh;
  var rows=d.recent||[];
  var tb='<table><thead><tr><th>Date</th><th>Colour</th><th>ATR%</th><th>Manip</th><th>Reversal</th><th>R:R</th><th>Outcome</th><th>P&amp;L</th></tr></thead><tbody>';
  for(var i=0;i<rows.length;i++){var x=rows[i];
   tb+='<tr><td>'+x.date+'</td><td>'+(x.candle_colour||'--')+'</td><td>'+(x.atr_pct||'--')+'</td><td>'+(x.manip_candle||'--')+'</td>'+
       '<td>'+(x.reversal_type&&x.reversal_type!=='NONE'?x.reversal_type:(x.reversal_found||'--'))+'</td>'+
       '<td>'+(x.rr_ratio||'--')+'</td><td class="'+ocls(x.outcome)+'">'+(x.outcome||'--')+'</td>'+
       '<td>'+(x.pnl_gbp!==''&&x.pnl_gbp!=null?((x.pnl_gbp>=0?'+':'')+x.pnl_gbp):'--')+'</td></tr>';
  }
  tb+='</tbody></table>';
  document.getElementById('logtbl').innerHTML=tb;
 }).catch(function(e){});
}
function brief(){var el=document.getElementById('brief');
 if(el.style.display==='block'){el.style.display='none';return;}
 fetch('/api/archie-brief').then(function(r){return r.text();}).then(function(t){el.textContent=t;el.style.display='block';});
}
load();setInterval(load,15000);
</script>
</body></html>"""


if __name__ == "__main__":
    log.info("USQuickFlip shadow collector starting -- initial data fetch...")
    refresh()
    threading.Thread(target=_loop, daemon=True, name="qf-poller").start()
    log.info("Dashboard -> http://localhost:%d", PORT)
    app.run(host="0.0.0.0", port=PORT, threaded=True)
