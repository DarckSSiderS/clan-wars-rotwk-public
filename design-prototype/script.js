document.addEventListener('DOMContentLoaded',()=>{
 const h=document.querySelector('.hamb'),nav=document.querySelector('.navlinks');if(h&&nav)h.onclick=()=>nav.classList.toggle('open');
 // Generic tabs
 document.querySelectorAll('[data-tabs]').forEach(group=>{
   group.querySelectorAll('[data-tab]').forEach(btn=>btn.addEventListener('click',()=>{
     const key=btn.dataset.tab;
     group.querySelectorAll('[data-tab]').forEach(x=>x.classList.toggle('active',x===btn));
     document.querySelectorAll(`[data-tab-panel]`).forEach(p=>{if(p.closest('body'))p.classList.toggle('active',p.dataset.tabPanel===key)});
   }));
 });
 document.querySelectorAll('[data-switch-tab]').forEach(btn=>btn.onclick=()=>{
   const key=btn.dataset.switchTab;const tab=document.querySelector(`[data-tab="${key}"]`);if(tab){tab.click();window.scrollTo({top:document.querySelector('.tabs').offsetTop-80,behavior:'smooth'})}
 });
 // Map territory selection
 document.querySelectorAll('.territory').forEach(t=>t.addEventListener('click',()=>{
   document.querySelectorAll('.territory').forEach(x=>x.classList.remove('active'));t.classList.add('active');
   const n=document.querySelector('[data-territory-name]'),c=document.querySelector('[data-territory-clan]'),i=document.querySelector('[data-territory-income]');
   if(n)n.textContent=t.dataset.name||'';if(c)c.textContent=t.dataset.clan||'';if(i)i.textContent=t.dataset.income||'';
 }));
 // Simple active filters
 document.querySelectorAll('.filters,.tool-group').forEach(g=>g.querySelectorAll('.filter,.tool').forEach(b=>b.onclick=()=>{g.querySelectorAll('.filter,.tool').forEach(x=>x.classList.remove('active'));b.classList.add('active')}));
 // Clan search
 const cs=document.querySelector('[data-clan-search]');if(cs)cs.addEventListener('input',()=>{const q=cs.value.toLowerCase();document.querySelectorAll('[data-clan-item]').forEach(x=>x.style.display=x.dataset.name.includes(q)?'':'none')});
 // Relic rarity filter
 const rf=document.querySelector('[data-rarity-filter]');if(rf)rf.onchange=()=>document.querySelectorAll('[data-relic]').forEach(x=>x.style.display=(rf.value==='all'||x.dataset.rarity===rf.value)?'':'none');
 // Relic modal
 const modal=document.querySelector('[data-relic-modal]');document.querySelectorAll('[data-relic-open]').forEach(b=>b.onclick=()=>{if(!modal)return;modal.classList.add('open');const t=modal.querySelector('[data-modal-title]');if(t)t.textContent=b.dataset.relicOpen});document.querySelectorAll('[data-modal-close]').forEach(b=>b.onclick=()=>modal&&modal.classList.remove('open'));if(modal)modal.onclick=e=>{if(e.target===modal)modal.classList.remove('open')};
 // Admin navigation
 document.querySelectorAll('[data-admin-target]').forEach(btn=>btn.onclick=()=>{const key=btn.dataset.adminTarget;document.querySelectorAll('[data-admin-target]').forEach(x=>x.classList.toggle('active',x===btn));document.querySelectorAll('[data-admin-panel]').forEach(p=>p.classList.toggle('active',p.dataset.adminPanel===key))});
});