/* profile-menu-fix.js
   Fix for profile three-dot menu: fetches real profile details from Firebase
   and shows a popover with user information.
   - Works with either modular (v9) admin pattern that sets window._db/_ref/_get/_onValue
     or with legacy firebase namespace (firebase.database()).
   - Tries to infer current user id from several common places.
*/
(function(){
  'use strict';

  const ID = 'aura-profile-popover';

  function $(s,root=document){return root.querySelector(s)}
  function createEl(tag, attrs={}, html=''){
    const el = document.createElement(tag);
    for(const k in attrs) el.setAttribute(k, attrs[k]);
    if(html) el.innerHTML = html;
    return el;
  }

  function inferUid(){
    // common places
    if(window.CURRENT_UID) return window.CURRENT_UID;
    if(window._uid) return window._uid;
    if(window._currentUid) return window._currentUid;
    try{ const ls = localStorage.getItem('uid') || localStorage.getItem('userId') || localStorage.getItem('currentUid'); if(ls) return ls; }catch(e){}
    // look for element data-uid
    const profileEl = document.querySelector('[data-uid], [data-userid], [data-user-id]');
    if(profileEl) return profileEl.dataset.uid || profileEl.dataset.userid || profileEl.dataset.userId;
    // try firebase auth
    try{
      if(window.firebase && firebase.auth && firebase.auth().currentUser) return firebase.auth().currentUser.uid;
      if(window._auth && _auth.currentUser) return _auth.currentUser.uid;
      if(window._user && window._user.uid) return window._user.uid;
    }catch(e){}
    return null;
  }

  function getFirebaseProfile(uid){
    return new Promise((resolve,reject)=>{
      if(!uid) return reject('uid-missing');

      // Use admin-style helpers if available (set in admin.html: _db, _ref, _get, _onValue)
      if(window._db && window._ref && window._get){
        try{
          const dbref = _ref(_db, `users/${uid}/profile`);
          _get(dbref).then(snapshot=>{
            const v = (snapshot && snapshot.val) ? snapshot.val() : (snapshot && snapshot.exists && snapshot.exists()? snapshot.val(): null);
            resolve(v||null);
          }).catch(err=>reject(err));
          return;
        }catch(e){}
      }

      // Fallback to realtime DB global (firebase v8 style)
      try{
        if(window.firebase && firebase.database){
          firebase.database().ref(`users/${uid}/profile`).once('value').then(snap=>resolve(snap.val())).catch(reject);
          return;
        }
      }catch(e){}

      // Cannot read
      reject('firebase-not-found');
    });
  }

  function buildPopover(data){
    // remove existing
    const existing = document.getElementById(ID);
    if(existing) existing.remove();

    const wrap = createEl('div',{id:ID});
    Object.assign(wrap.style,{position:'absolute',zIndex:99999,background:'#fff',color:'#111',minWidth:'260px',borderRadius:'12px',boxShadow:'0 10px 30px rgba(0,0,0,0.18)',padding:'12px',fontFamily:'Arial,Helvetica,sans-serif'});

    const top = createEl('div',{},`
      <div style="display:flex;gap:12px;align-items:center">
        <div style="width:56px;height:56px;border-radius:50%;overflow:hidden;background:#eee;flex-shrink:0">
          <img id="aura-pop-avatar" src="${escapeHtml(data?.photo||data?.pic||'') }" style="width:100%;height:100%;object-fit:cover" onerror="this.src='https://via.placeholder.com/56'">
        </div>
        <div style="flex:1;min-width:0">
          <div style="font-weight:700;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeHtml(data?.name||data?.displayName||data?.fullname||'Unknown')}</div>
          <div style="font-size:12px;color:#666;margin-top:4px">${escapeHtml(data?.status||data?.bio||'No status')}</div>
        </div>
      </div>
    `);

    const rows = [];
    rows.push(fieldRow('Phone', data?.phone || data?.phoneNumber || '—'));
    if(data?.email) rows.push(fieldRow('Email', data.email));
    if(data?.location) rows.push(fieldRow('Location', data.location));
    if(data?.joinedAt) rows.push(fieldRow('Joined', new Date(data.joinedAt*1000).toLocaleString()));
    if(data?.createdAt) rows.push(fieldRow('Created', new Date(data.createdAt).toLocaleString()));

    const mid = createEl('div',{}, rows.join(''));
    mid.style.marginTop='10px';

    const actions = createEl('div',{},`
      <div style="display:flex;gap:8px;margin-top:10px">
        <button id="aura-view-profile" style="flex:1;padding:9px;border-radius:10px;border:1px solid #e6e6e6;background:#fff;cursor:pointer">View Profile</button>
        <button id="aura-edit-profile" style="flex:1;padding:9px;border-radius:10px;border:0;background:linear-gradient(90deg,#0088cc,#00b4e6);color:#fff;cursor:pointer">Edit</button>
      </div>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button id="aura-blocks" style="flex:1;padding:9px;border-radius:10px;border:1px solid #f3f3f3;background:#fff;cursor:pointer">Blocked</button>
        <button id="aura-logout" style="flex:1;padding:9px;border-radius:10px;border:1px solid #f3f3f3;background:#fff;cursor:pointer">Logout</button>
      </div>
    `);

    wrap.appendChild(top);
    wrap.appendChild(mid);
    wrap.appendChild(actions);

    document.body.appendChild(wrap);

    // Wire actions to existing functions if present
    $('#aura-view-profile',wrap).addEventListener('click',()=>{
      if(window.openProfileModal) return window.openProfileModal(data);
      alert('Profile:\n'+JSON.stringify(data,null,2));
    });
    $('#aura-edit-profile',wrap).addEventListener('click',()=>{
      if(window.openEditProfile) return window.openEditProfile(data);
      alert('Edit profile not implemented in app');
    });
    $('#aura-blocks',wrap).addEventListener('click',()=>{
      if(window.openBlockedList) return window.openBlockedList();
      alert('No blocked users UI');
    });
    $('#aura-logout',wrap).addEventListener('click',()=>{
      if(window.doLogout) return window.doLogout();
      if(window.firebase && firebase.auth){ firebase.auth().signOut(); alert('Signed out'); }
      else alert('Logout not available');
    });

    // click outside to close
    setTimeout(()=>{
      function docClick(e){ if(!wrap.contains(e.target)) { wrap.remove(); document.removeEventListener('click',docClick); } }
      document.addEventListener('click',docClick);
    },200);

    return wrap;
  }

  function fieldRow(label,val){
    return `<div style="display:flex;justify-content:space-between;padding:6px 0;border-top:1px solid #fafafa">
        <div style="color:#666;font-size:13px">${escapeHtml(label)}</div>
        <div style="font-weight:600;font-size:13px;color:#111">${escapeHtml(val||'—')}</div>
    </div>`;
  }

  function escapeHtml(s){ if(s==null) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

  function positionPopover(el, pop){
    try{
      const r = el.getBoundingClientRect();
      const pw = pop.offsetWidth; const ph = pop.offsetHeight;
      let left = r.right - pw; if(left<8) left=8;
      let top = r.bottom + 8; if(top+ph>window.innerHeight) top = r.top - ph - 8;
      pop.style.left = left + 'px'; pop.style.top = top + 'px';
    }catch(e){}
  }

  function onProfileBtnClick(e){
    e.preventDefault(); e.stopPropagation();
    const btn = e.currentTarget;
    const uid = inferUid();
    if(!uid){ alert('Could not determine current user id'); return; }
    getFirebaseProfile(uid).then(profile=>{
      const pop = buildPopover(profile || {});
      positionPopover(btn, pop);
    }).catch(err=>{
      const pop = buildPopover({name:'Unknown', phone:'—', status: String(err)});
      positionPopover(btn,pop);
    });
  }

  function wireButtons(){
    // find candidate elements
    const selectors = ['[data-action="profile-menu"]','[data-action="three-dots"]','.profile-dots','.profile-menu-btn', '.fa-ellipsis-v', '.fa-ellipsis-h'];
    const found = new Set();
    selectors.forEach(sel=>{
      document.querySelectorAll(sel).forEach(el=>{
        if(found.has(el)) return; found.add(el);
        el.style.cursor='pointer';
        el.addEventListener('click', onProfileBtnClick);
      });
    });

    // also try within header/profile area
    const header = document.querySelector('#me, #my-profile, .my-profile, .profile');
    if(header){ const el = header.querySelector('.dots, .three-dots, .menu-dots, .fa-ellipsis-v'); if(el){ el.style.cursor='pointer'; el.addEventListener('click', onProfileBtnClick); }}
  }

  // Wait for DOM ready
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',wireButtons); else wireButtons();

  // Also re-run wiring when DOM changes (in case view is built dynamically)
  const obs = new MutationObserver((m)=>{ wireButtons(); });
  obs.observe(document.body,{childList:true,subtree:true});
})();
