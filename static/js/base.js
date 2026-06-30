/* ═══════════════════════════════════════════════
   FairEx — base.js  (shared across all pages)
   ═══════════════════════════════════════════════ */
var L = "logo.png";
var currentTheme = localStorage.getItem('fairex-theme') || 'dark';

function applyTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  currentTheme = t;
  localStorage.setItem('fairex-theme', t);
  var icon  = document.getElementById('themeIcon');
  var label = document.getElementById('themeLabel');
  if (t === 'light') {
    if(icon)  icon.textContent  = '🌙';
    if(label) label.textContent = 'Dark';
  } else {
    if(icon)  icon.textContent  = '☀️';
    if(label) label.textContent = 'Light';
  }
}
function toggleTheme() { applyTheme(currentTheme === 'dark' ? 'light' : 'dark'); }

/* Logo: try image, fallback to shield SVG so navbar never breaks */
function setLogos() {
  function trySet(el) {
    if(!el) return;
    el.src = L;
    el.onerror = function(){
      this.style.display='none';
    };
  }
  trySet(document.getElementById("nav-logo"));
  trySet(document.getElementById("hero-logo"));
  document.querySelectorAll(".all-logo").forEach(function(el){
    el.src = L;
    el.onerror = function(){ this.style.display='none'; };
  });
}

function spawnPt() {
  document.querySelectorAll(".ptcls").forEach(function(c) {
    if (c.children.length > 3) return;
    for (var i = 0; i < 18; i++) {
      var d = document.createElement("div"); d.className = "pt";
      var sz = 1.5 + Math.random() * 3;
      d.style.cssText = "width:"+sz+"px;height:"+sz+"px;left:"+(Math.random()*100)+"%;background:rgba(80,130,255,"+(0.15+Math.random()*0.3)+");animation-duration:"+(8+Math.random()*10)+"s;animation-delay:"+(Math.random()*9)+"s";
      c.appendChild(d);
    }
  });
}

function tpw(id) {
  var i = document.getElementById(id);
  if(i) i.type = (i.type === "password") ? "text" : "password";
}

document.addEventListener('DOMContentLoaded', function() {
  applyTheme(currentTheme);
  setLogos();
});
