(async function () {
  "use strict";
  const id = "pixel-drummer", proxy = "pixel-band-proxy";
  const ours = new Set([proxy,"pixel-drummer-nayu"]);
  const bridge = window.__astraPluginBridge?.[id];
  const native = window.__TAURI_INTERNALS__;
  if (!bridge || !native?.invoke) return;
  const oldCleanup = window.__astraPluginCleanup?.[id];
  if (oldCleanup) await oldCleanup();
  document.getElementById("pixel-drummer-controls")?.remove();
  const previousKey = "pixel-drummer-previous-character";
  const modeKey = "pixel-drummer-mode";
  let timer, busy=false, stopped=false, engaged=false;
  let hiddenSide=false, lastHidden=0;
  const call = (method,params={}) => bridge.callBackend(method,params);
  const report = async payload => {
    try { await call("report",{payload:{visible_panel:false,...payload}}); } catch (_) {}
  };
  async function wear(target) {
    const result=await native.invoke("run_character_verb",{verb:{wear:{id:target}}});
    if (!result.ok || !result.confirmed || result.volatile)
      throw new Error(result.detail || result.error_code || "Смена персонажа не подтверждена");
    for (let n=0;n<30;n++) {
      const library=await native.invoke("list_characters",{});
      if (library.active_id===target) return;
      await new Promise(resolve=>setTimeout(resolve,100));
    }
    throw new Error("Astra ещё не подтвердила нового персонажа");
  }
  async function restore() {
    const library=await native.invoke("list_characters",{});
    if (ours.has(library.active_id)) {
      const previous=localStorage.getItem(previousKey);
      const target=library.characters.some(c=>c.id===previous && !ours.has(c.id))
        ? previous : "builtin:nayu-2d";
      // Restore first; don't touch a user's manually selected character.
      await wear(target);
    }
    await call("stop_renderer");
    engaged=false;
    localStorage.removeItem(previousKey);
  }
  async function operate(mode,startup=false,payload={}) {
    if (busy || stopped) return;
    busy=true;
    try {
      if (!["auto","slow","mid","fast","walk","restore","concert"].includes(mode))
        throw new Error("Неизвестный режим");
      if (engaged && mode!=="restore") {
        // A mode change does not need to reinstall assets or change the native
        // character again. Keep the existing renderer and its leased control.
        const state=await call("configure",{payload:{...payload,mode,visible:true}});
        if (state.ready) {
          localStorage.setItem(modeKey,mode);
          await report({mode,ok:true,character:proxy,renderer:state.detail});
          return;
        }
        throw new Error("Рендерер перестал отвечать при смене режима");
      }
      const before=await native.invoke("list_characters",{});
      if (mode==="restore") {
        await restore();
        localStorage.setItem(modeKey,mode);
        await report({mode,ok:true});
        return;
      }
      if (!before.available || !before.can_run_verbs)
        throw new Error("Компаньон недоступен");
      if (startup && !["builtin:nayu-2d",...ours].includes(before.active_id)) {
        await report({mode,skipped:true,reason:"Выбран другой персонаж"});
        return;
      }
      const prepared=await call("prepare");
      if (!prepared.renderer?.ready) throw new Error("Рендерер не готов");
      if (stopped) return;
      if (before.active_id!==proxy) {
        if (before.active_id && !ours.has(before.active_id))
          localStorage.setItem(previousKey,before.active_id);
        await wear(proxy);
      }
      const cue=await native.invoke("cue_animation",{mode:"state",value:"stage_hidden_a"});
      if (!cue.sent) throw new Error("Astra не приняла временное скрытие штатного спрайта");
      hiddenSide=false;lastHidden=Date.now();
      const state=await call("configure",{payload:{...payload,mode,visible:true}});
      if (!state.ready) throw new Error("Рендерер остановился при запуске");
      engaged=true;
      localStorage.setItem(modeKey,mode);
      await report({mode,ok:true,character:proxy,renderer:state.detail});
    } catch (error) {
      try { await restore(); } catch (restoreError) {
        await report({mode,error:String(error),restore_error:String(restoreError)});
        return;
      }
      await report({mode,error:String(error),restored:true});
    } finally { busy=false; }
  }
  window.__astraPluginCleanup ??= {};
  window.__astraPluginCleanup[id]=async () => {
    if (stopped) return;
    stopped=true;
    clearInterval(timer);
    for (let n=0;busy && n<100;n++) await new Promise(r=>setTimeout(r,100));
    try { await restore(); } catch (_) {}
  };
  await operate(localStorage.getItem(modeKey)||"auto",true);
  if (stopped) return;
  timer=setInterval(async () => {
    if (busy || stopped) return;
    busy=true;
    let operation,operationPayload;
    try {
      const status=await call("status");
      operation=status.operation;
      operationPayload=status.operation_payload;
      if (engaged) {
        const library=await native.invoke("list_characters",{});
        if (library.active_id!==proxy) {
          await call("stop_renderer");engaged=false;
          localStorage.setItem(modeKey,"restore");
          localStorage.removeItem(previousKey);
        } else if (!status.renderer?.ready) {
          await restore();
          await report({error:"Рендерер перестал отвечать",restored:true});
        } else if (Date.now()-lastHidden>1000) {
          hiddenSide=!hiddenSide;
          const cue=await native.invoke("cue_animation",{mode:"state",value:hiddenSide?"stage_hidden_b":"stage_hidden_a"});
          if (!cue.sent) throw new Error("Astra не приняла heartbeat сцены");
          lastHidden=Date.now();
        }
      }
    } catch (error) {
      if (engaged) {
        try {
          const library=await native.invoke("list_characters",{});
          if (library.active_id===proxy)
            await wear(localStorage.getItem(previousKey)||"builtin:nayu-2d");
        } catch (_) {}
        engaged=false;
      }
    } finally { busy=false; }
    if (operation) await operate(operation,false,operationPayload);
  },500);
})();
