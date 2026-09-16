from __future__ import annotations

import html as html_lib
import logging
import tempfile
import time
from pathlib import Path

from ....application.dto import (
    ExportNotesCommand,
    InsertClarificationCommand,
    RenameSessionCommand,
    UpdateNotesCommand,
)
from ....domain.errors import DomainError, NoClarificationAvailable
from ....domain.value_objects.identifiers import SessionId
from ....infrastructure.dependency_injection.container import Container
from ..keyboard import shortcuts as shortcut_registry

logger = logging.getLogger(__name__)

STUDENT_CSS = """
/* Oculta el pie de Gradio y accesos tecnicos que no forman parte de la app. */
footer,
.api-docs,
.built-with,
a[href*="gradio.app"],
button[aria-label="Code"],
button[aria-label="View API"],
button[aria-label="Show API"],
.api,
.show-api,
.fixed.bottom-0,
.fixed.bottom-4 {
  display: none !important;
}

html, body, .gradio-container {
  background: #f3f6fb !important;
  color: #172033 !important;
  font-family: system-ui, -apple-system, "Segoe UI Variable", "Segoe UI", sans-serif !important;
  font-size: 24px !important;
  min-height: 100dvh !important;
  height: auto !important;
  overflow-x: hidden !important;
  overflow-y: auto !important;
}

.gradio-container button {
  font-size: 24px !important;
}

.gradio-container {
  width: 100vw !important;
  max-width: none !important;
  height: auto !important;
  min-height: 100dvh !important;
  margin: 0 !important;
  padding: 16px 28px !important;
  overflow: visible !important;
}

.gradio-container h1 {
  margin: 0 0 18px !important;
  color: #111827 !important;
  font-size: 2rem !important;
  font-weight: 800 !important;
  letter-spacing: 0 !important;
}

.gradio-container .block,
.gradio-container .form,
.gradio-container .panel {
  border-color: #d5deeb !important;
  box-shadow: none !important;
}

.gradio-container > div,
.gradio-container .main {
  max-height: none !important;
  overflow: visible !important;
}

textarea[readonly] { user-select: text !important; }
#announce-slide-btn,
#insert-clar-btn,
#jump-slide-notes-btn,
#slide-sync,
#tts-audio,
#beep-trigger,
#puente-locucion,
#descarga-trigger {
  display: none !important;
}
.sr-focus :focus-visible { outline: 3px solid #1a73e8 !important; outline-offset: 2px !important; }

/* Region viva accesible: invisible para la vista -el diseno no cambia- pero
   presente en el arbol de accesibilidad, que es donde tiene que estar. */
#region-anuncios {
  position: absolute !important; left: -10000px !important; top: auto !important;
  width: 1px !important; height: 1px !important; overflow: hidden !important;
}

/* Ajustes de contraste para los textos generados por Gradio. */
.gradio-container,
.gradio-container label,
.gradio-container textarea,
.gradio-container input,
.gradio-container button,
.gradio-container span,
.gradio-container p,
.gradio-container small {
  color: #172033 !important;
}

.gradio-container [style*="color"],
.gradio-container [class*="text-gray"],
.gradio-container [class*="text-slate"],
.gradio-container [class*="secondary"],
.gradio-container [class*="disabled"] {
  color: #172033 !important;
}

.gradio-container button:disabled,
.gradio-container input:disabled,
.gradio-container textarea:disabled {
  color: #334155 !important;
  opacity: 1 !important;
}

.gradio-container textarea::placeholder,
.gradio-container input::placeholder {
  color: #334155 !important;
  opacity: 1 !important;
}
.gradio-container button.primary,
.gradio-container .primary {
  color: #ffffff !important;
}
#respuesta-llm label,
#notas-alumno label {
  color: #3730a3 !important;
}
.field-heading {
  margin: 0 0 0.45rem 0 !important;
  color: #1e3a8a !important;
  font-size: 1.02rem !important;
  font-weight: 700 !important;
}

#respuesta-llm,
#notas-alumno {
  background: #ffffff !important;
  border: 1px solid #d5deeb !important;
  border-radius: 8px !important;
}

#respuesta-llm textarea,
#notas-alumno textarea {
  background: #ffffff !important;
  color: #111827 !important;
  border: 1px solid #cbd5e1 !important;
  border-radius: 8px !important;
  font-size: 1rem !important;
  line-height: 1.55 !important;
}

#respuesta-llm textarea {
  height: clamp(78px, 13dvh, 112px) !important;
  min-height: 78px !important;
  max-height: 112px !important;
  overflow-y: auto !important;
}

#notas-alumno textarea {
  height: clamp(130px, calc(100dvh - 520px), 42dvh) !important;
  min-height: 130px !important;
  max-height: 42dvh !important;
  overflow-y: auto !important;
}

#respuesta-llm textarea:focus,
#notas-alumno textarea:focus {
  border-color: #2563eb !important;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.2) !important;
}

#descargar-notas-btn button,
#descargar-notas-formateadas-btn button {
  min-height: 46px !important;
  border-radius: 8px !important;
  border: 1px solid #b7c4d6 !important;
  background: #ffffff !important;
  color: #172033 !important;
  font-weight: 700 !important;
}

#descargar-notas-btn button:hover,
#descargar-notas-formateadas-btn button:hover {
  background: #eaf1ff !important;
  border-color: #2563eb !important;
}

#escuchar-btn button {
  min-height: 46px !important;
  border-radius: 8px !important;
  background: #1d4ed8 !important;
  border: 1px solid #1d4ed8 !important;
  color: #ffffff !important;
  font-weight: 800 !important;
}

/* Capa visual de la plataforma del alumno. */
.student-shell {
  width: 100% !important;
  height: auto !important;
  min-height: calc(100dvh - 112px) !important;
  margin: 0 0 24px !important;
  gap: 12px !important;
  overflow: visible !important;
}

.student-header {
  background: #ffffff;
  border: 1px solid #d7e0ec;
  border-radius: 8px;
  padding: 14px 20px;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
  margin-bottom: 12px;
}

.student-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  flex-wrap: wrap;
}

.student-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.student-settings-button {
  width: 42px;
  height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 42px;
  border: 1px solid #b7c4d6;
  border-radius: 8px;
  background: #ffffff;
  color: #172033;
  font-size: 1.35rem;
  line-height: 1;
  cursor: pointer;
}

.student-settings-button:hover {
  background: #eaf1ff;
  border-color: #2563eb;
}

.student-settings-button:focus-visible {
  outline: 3px solid #1a73e8;
  outline-offset: 2px;
}

.student-settings-panel {
  position: fixed;
  z-index: 1000;
  top: 78px;
  right: 28px;
  width: min(320px, calc(100vw - 32px));
  padding: 16px;
  border: 1px solid #b7c4d6;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 14px 32px rgba(15, 23, 42, 0.18);
}

.student-settings-panel[hidden] {
  display: none !important;
}

.student-settings-title {
  margin: 0 0 14px;
  color: #111827;
  font-size: 1.1rem;
  font-weight: 800;
}

.student-setting {
  display: grid;
  gap: 7px;
  margin-top: 12px;
}

.student-setting label,
.student-setting-label {
  color: #172033;
  font-weight: 700;
}

.student-setting select {
  width: 100%;
  min-height: 42px;
  padding: 7px 10px;
  border: 1px solid #94a3b8;
  border-radius: 6px;
  background: #ffffff;
  color: #172033;
  font: inherit;
}

.student-setting-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 42px;
  cursor: pointer;
}

.student-setting-toggle input {
  width: 20px;
  height: 20px;
  margin: 0;
  accent-color: #1d4ed8;
}

.student-title {
  margin: 0;
  color: #111827;
  font-size: 1.5rem;
  font-weight: 850;
  letter-spacing: 0;
  line-height: 1.1;
}

.student-status-pill {
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  color: #1e3a8a;
  border-radius: 999px;
  padding: 8px 14px;
  font-size: 0.9rem;
  font-weight: 700;
  white-space: nowrap;
}

.student-panel {
  background: #ffffff;
  border: 1px solid #d7e0ec;
  border-radius: 8px;
  padding: 14px 16px;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.07);
  overflow: hidden !important;
}

.clarification-panel {
  border-left: 5px solid #2563eb;
  min-height: 0 !important;
  flex: 0 0 clamp(185px, 28dvh, 245px) !important;
}

.notes-panel {
  border-left: 5px solid #059669;
  flex: 0 0 auto !important;
  min-height: 0 !important;
}

.panel-title-row {
  display: flex;
  align-items: center;
  gap: 0;
  margin-bottom: 10px;
}

.field-heading {
  margin: 0 !important;
  color: #111827 !important;
  font-size: 1.1rem !important;
  font-weight: 800 !important;
}

.student-actions {
  gap: 12px !important;
  flex-shrink: 0 !important;
  margin-top: 10px !important;
}

@media (max-height: 680px) {
  .gradio-container {
    padding: 10px 18px !important;
  }
  .student-header {
    padding: 10px 16px !important;
    margin-bottom: 8px !important;
  }
  .student-title {
    font-size: 1.22rem !important;
  }
  .student-status-pill,
  .field-caption {
    display: none !important;
  }
  .student-shell {
    height: auto !important;
    min-height: calc(100dvh - 62px) !important;
    gap: 8px !important;
  }
  .student-panel {
    padding: 10px 12px !important;
  }
  .clarification-panel {
    flex-basis: 150px !important;
  }
  .panel-title-row {
    margin-bottom: 6px !important;
  }
  .field-heading {
    font-size: 0.98rem !important;
  }
  #respuesta-llm textarea {
    height: 64px !important;
    min-height: 64px !important;
    max-height: 64px !important;
  }
  #notas-alumno textarea {
    height: calc(100dvh - 388px) !important;
    min-height: 96px !important;
    max-height: calc(100dvh - 388px) !important;
  }
  #descargar-notas-btn button,
  #descargar-notas-formateadas-btn button,
  #escuchar-btn button {
    min-height: 38px !important;
  }
}

@media (max-width: 760px) {
  .gradio-container {
    width: 100% !important;
    padding: 16px !important;
  }
  .student-header,
  .student-panel {
    padding: 16px !important;
  }
  .student-title {
    font-size: 1.35rem !important;
  }
  .student-settings-panel {
    top: 70px;
    right: 16px;
  }
}
"""

STUDENT_JS = """
() => {
  document.title = 'Cognitive Agent';
  if (window.__caAlumnoListo) return;
  window.__caAlumnoListo = true;

  /* ---------- preferencias del alumno ---------- */
  const PREFERENCIAS_CLAVE = 'cognitive-agent.student.preferences.v1';
  const VELOCIDADES = [1, 1.5, 2, 3];
  const preferencias = { velocidad: 1, avisoSonoro: true };

  try {
    const guardadas = JSON.parse(window.localStorage.getItem(PREFERENCIAS_CLAVE) || '{}');
    const velocidad = Number(guardadas.velocidad);
    if (VELOCIDADES.includes(velocidad)) preferencias.velocidad = velocidad;
    if (typeof guardadas.avisoSonoro === 'boolean') {
      preferencias.avisoSonoro = guardadas.avisoSonoro;
    }
  } catch (e) {}

  const guardarPreferencias = () => {
    try {
      window.localStorage.setItem(PREFERENCIAS_CLAVE, JSON.stringify(preferencias));
    } catch (e) {}
  };

  const cerrarAjustes = (devolverFoco = false) => {
    const boton = document.getElementById('student-settings-btn');
    const panel = document.getElementById('student-settings-panel');
    if (!boton || !panel || panel.hidden) return;
    panel.hidden = true;
    boton.setAttribute('aria-expanded', 'false');
    if (devolverFoco) boton.focus();
  };

  const prepararAjustes = () => {
    const boton = document.getElementById('student-settings-btn');
    const panel = document.getElementById('student-settings-panel');
    const velocidad = document.getElementById('student-reading-rate');
    const aviso = document.getElementById('student-sound-enabled');
    if (!boton || !panel || !velocidad || !aviso || boton.dataset.preparado === '1') return;

    boton.dataset.preparado = '1';
    velocidad.value = String(preferencias.velocidad);
    aviso.checked = preferencias.avisoSonoro;

    boton.addEventListener('click', () => {
      const abrir = panel.hidden;
      panel.hidden = !abrir;
      boton.setAttribute('aria-expanded', String(abrir));
      if (abrir) velocidad.focus();
    });
    velocidad.addEventListener('change', () => {
      const nueva = Number(velocidad.value);
      if (VELOCIDADES.includes(nueva)) preferencias.velocidad = nueva;
      guardarPreferencias();
    });
    aviso.addEventListener('change', () => {
      preferencias.avisoSonoro = aviso.checked;
      guardarPreferencias();
    });
    document.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape' && !panel.hidden) {
        ev.preventDefault();
        cerrarAjustes(true);
      }
    });
    document.addEventListener('click', (ev) => {
      if (!panel.hidden && !panel.contains(ev.target) && !boton.contains(ev.target)) {
        cerrarAjustes(false);
      }
    });
  };
  prepararAjustes();

  /* ---------- aviso sonoro ---------- */
  window._beepCtx = null;
  const initBeep = () => {
    if (!window._beepCtx) {
      try { window._beepCtx = new (window.AudioContext || window.webkitAudioContext)(); }
      catch (e) {}
    }
    if (window._beepCtx && window._beepCtx.state === 'suspended') {
      window._beepCtx.resume().catch(() => {});
    }
  };
  document.addEventListener('click', initBeep, true);
  document.addEventListener('keydown', initBeep, true);

  const beep = () => {
    const ctx = window._beepCtx;
    if (!ctx || ctx.state !== 'running') return;
    try {
      const osc = ctx.createOscillator(), gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.frequency.value = 880; osc.type = 'sine';
      gain.gain.setValueAtTime(0.25, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.18);
      osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.18);
    } catch (e) {}
  };

  const campo = (id) => {
    const raiz = document.getElementById(id);
    return raiz ? raiz.querySelector('textarea, input') : null;
  };

  const puente = (id) => {
    const raiz = document.getElementById(id);
    if (!raiz) return '';
    const htmlBridge = raiz.querySelector('[data-value]');
    if (htmlBridge) return htmlBridge.getAttribute('data-value') || '';
    const control = raiz.querySelector('textarea, input');
    return control ? control.value : '';
  };

  const asociarEtiqueta = (id, texto) => {
    const raiz = document.getElementById(id);
    if (!raiz) return;
    const controles = raiz.querySelectorAll('textarea, input');
    if (!controles.length) return;
    controles.forEach((control, indice) => {
      const controlId = indice === 0 ? id + '-control' : id + '-control-' + indice;
      control.id = control.id || controlId;
      control.setAttribute('aria-label', texto);
    });
    const label = raiz.querySelector('label');
    if (label) label.setAttribute('for', controles[0].id);
  };

  const sanearFormularios = () => {
    asociarEtiqueta('respuesta-llm', 'Aclaración');
    asociarEtiqueta('notas-alumno', 'Notas del alumno');

    document.querySelectorAll('textarea, input, select').forEach((control, indice) => {
      if (control.closest('#beep-trigger, #puente-locucion, #descarga-trigger, #slide-sync, #tts-audio')) {
        return;
      }
      if (!control.id) control.id = 'ca-control-' + indice;
      const tieneNombre = control.getAttribute('aria-label')
        || control.getAttribute('aria-labelledby')
        || document.querySelector('label[for="' + CSS.escape(control.id) + '"]');
      if (tieneNombre) return;
      const texto = control.getAttribute('placeholder')
        || control.getAttribute('title')
        || control.getAttribute('name')
        || 'Control de la interfaz del alumno';
      control.setAttribute('aria-label', texto);
    });

    document.querySelectorAll('label').forEach((label) => {
      const destino = label.getAttribute('for');
      const envuelveControl = label.querySelector('input, textarea, select');
      if (destino && document.getElementById(destino)) return;
      if (envuelveControl) return;
      label.remove();
    });
  };

  const refrescarEtiquetas = () => {
    sanearFormularios();
  };
  refrescarEtiquetas();
  setTimeout(refrescarEtiquetas, 500);
  setTimeout(refrescarEtiquetas, 1500);
  new MutationObserver(() => refrescarEtiquetas()).observe(document.body, {
    childList: true,
    subtree: true
  });

  const solicitarLecturaAutomatica = (intento = 0) => {
    const raiz = document.getElementById('escuchar-btn');
    const boton = raiz && (raiz.querySelector('button') || raiz);
    if (boton) {
      boton.click();
      return;
    }
    // Gradio inserta el boton al hacerlo visible y puede tardar unas decimas
    // mas que el puente que anuncia la nueva aclaracion.
    if (intento < 10) {
      setTimeout(() => solicitarLecturaAutomatica(intento + 1), 100);
    }
  };

  let ultimoBeep = '';
  setInterval(() => {
    const valor = puente('beep-trigger');
    if (!valor || valor === ultimoBeep) return;
    ultimoBeep = valor;
    if (preferencias.avisoSonoro) beep();
    else solicitarLecturaAutomatica();
  }, 300);

  /* ---------- locucion en el dispositivo del alumno ---------- */
  let ultimaLocucion = '';
  setInterval(() => {
    const valor = puente('puente-locucion');
    if (!valor || valor === ultimaLocucion) return;
    ultimaLocucion = valor;
    const texto = valor.slice(valor.indexOf('|') + 1).trim();
    if (!texto || !('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(texto);
    u.lang = 'es-ES';
    u.rate = preferencias.velocidad;
    window.speechSynthesis.speak(u);
  }, 300);

  /* ---------- descarga de apuntes ----------
     El servidor deja la URL en un disparador oculto y aqui se lanza la
     descarga. Es el mecanismo de la version anterior: gr.DownloadButton
     re-renderiza la columna al recibir su valor y lo acaba escribiendo en el
     campo de notas.                                                        */
  let ultimaDescarga = '';
  setInterval(() => {
    const valor = puente('descarga-trigger');
    if (!valor || valor === ultimaDescarga) return;
    ultimaDescarga = valor;
    const url = valor.slice(valor.indexOf('|') + 1);
    if (!url) return;
    fetch(url)
      .then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.blob(); })
      .then((blob) => {
        const partes = url.split('/');
        const nombre = decodeURIComponent(partes[partes.length - 1] || 'apuntes.txt');
        const objUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = objUrl; a.download = nombre;
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(objUrl), 5000);
      })
      .catch(() => {});
  }, 300);

  /* ---------- atajos: se leen del servidor, no van fijados aqui ---------- */
  const BOTON = {
    listen_clarification: 'escuchar-btn',
    announce_slide: 'announce-slide-btn',
    insert_clarification: 'insert-clar-btn',
    jump_to_slide_notes: 'jump-slide-notes-btn'
  };
  const coincide = (ev, combo) => {
    const partes = String(combo).split('+').map((p) => p.trim().toLowerCase());
    const tecla = partes[partes.length - 1];
    if (ev.altKey !== partes.includes('alt')) return false;
    if (ev.shiftKey !== partes.includes('shift')) return false;
    if (ev.ctrlKey !== (partes.includes('ctrl') || partes.includes('control'))) return false;
    return String(ev.key).toLowerCase() === tecla;
  };

  fetch('/api/config/accessibility')
    .then((r) => (r.ok ? r.json() : null))
    .then((cfg) => {
      const atajos = (cfg && cfg.shortcuts) || {
        listen_clarification: 'F7', announce_slide: 'F8',
        insert_clarification: 'F9', jump_to_slide_notes: 'F2'
      };
      window.addEventListener('keydown', (ev) => {
        if (ev.repeat) return;
        for (const [accion, combo] of Object.entries(atajos)) {
          if (!combo || !coincide(ev, combo)) continue;
          const raiz = document.getElementById(BOTON[accion]);
          const btn = raiz && (raiz.querySelector('button') || raiz);
          if (btn) { ev.preventDefault(); ev.stopPropagation(); btn.click(); }
          return;
        }
      }, true);
    })
    .catch(() => {});

  /* ---------- ocultar del lector lo que solo sirve de destino ---------- */
  ['announce-slide-btn', 'insert-clar-btn', 'jump-slide-notes-btn', 'tts-audio'].forEach((id) => {
    const raiz = document.getElementById(id);
    if (!raiz) return;
    raiz.setAttribute('aria-hidden', 'true');
    raiz.querySelectorAll('button, input, textarea, select, audio, [tabindex]')
        .forEach((el) => el.setAttribute('tabindex', '-1'));
  });

  /* ---------- proteccion de las marcas [Diapositiva N] (igual que antes) ---
     Se veta el borrado ANTES de que ocurra, en vez de repararlo despues.   */
  const protegerMarcas = () => {
    const f = campo('notas-alumno');
    if (!f) return false;
    if (f.dataset.protegido === '1') return true;
    f.dataset.protegido = '1';

    const RE = /\\[Diapositiva \\d+\\]/g;
    const VENTANA = 300;
    const rangos = (t) => {
      const r = []; let m; RE.lastIndex = 0;
      while ((m = RE.exec(t))) r.push([m.index, m.index + m[0].length]);
      return r;
    };
    const solapa = (a0, a1, b0, b1) => a0 < b1 && b0 < a1;

    let avisador = document.getElementById('aviso-marca');
    if (!avisador) {
      avisador = document.createElement('div');
      avisador.id = 'aviso-marca';
      avisador.setAttribute('aria-live', 'assertive');
      avisador.setAttribute('role', 'status');
      Object.assign(avisador.style, {
        position: 'absolute', left: '-10000px', width: '1px',
        height: '1px', overflow: 'hidden'
      });
      document.body.appendChild(avisador);
    }
    const avisar = () => {
      avisador.textContent = '';
      setTimeout(() => {
        avisador.textContent = 'No se puede borrar la marca de diapositiva.';
      }, 30);
    };

    const rangoBorrado = (tipo, ini, fin, largo) => {
      if (ini !== fin) return [ini, fin];
      if (tipo === 'deleteContentBackward') return [Math.max(0, ini - 1), ini];
      if (tipo === 'deleteContentForward') return [ini, Math.min(largo, ini + 1)];
      if (tipo && tipo.startsWith('delete')) {
        return tipo.toLowerCase().includes('forward')
          ? [ini, Math.min(largo, ini + VENTANA)]
          : [Math.max(0, ini - VENTANA), ini];
      }
      return null;
    };

    f.addEventListener('beforeinput', (ev) => {
      const ini = f.selectionStart, fin = f.selectionEnd;
      const marcas = rangos(f.value);
      if (!marcas.length) return;
      const r = rangoBorrado(ev.inputType, ini, fin, f.value.length);
      if (r) {
        if (marcas.some(([s, e]) => solapa(r[0], r[1], s, e))) {
          ev.preventDefault(); avisar();
        }
        return;
      }
      if (ini === fin && marcas.some(([s, e]) => ini > s && ini < e)) {
        ev.preventDefault(); avisar();
      }
    }, true);

    f.addEventListener('cut', (ev) => {
      const ini = f.selectionStart, fin = f.selectionEnd;
      if (ini === fin) return;
      if (rangos(f.value).some(([s, e]) => solapa(ini, fin, s, e))) {
        ev.preventDefault(); avisar();
      }
    }, true);

    return true;
  };
  if (!protegerMarcas()) {
    setTimeout(protegerMarcas, 300);
    setTimeout(protegerMarcas, 1200);
  }
}
"""

class StudentUiAdapter:

    def __init__(
        self, container: Container, session_id: SessionId, *, follow_latest: bool = False
    ) -> None:
        self._container = container
        self._session_id = session_id
        self._follow_latest = follow_latest

        self._titulo_visto: str | None = None

    def follow_latest_session(self) -> bool:
        if not self._follow_latest:
            return False
        active = sorted(
            self._container.sessions.list_active(), key=lambda session: session.started_at
        )
        if not active or active[-1].session_id == self._session_id:
            return False
        previous = self._session_id
        self._session_id = active[-1].session_id
        self._titulo_visto = None
        logger.info(
            "Interfaz del alumno cambiada de la sesion %s a la sesion %s.",
            previous.value,
            self._session_id.value,
        )
        return True

    def slide_label(self) -> str:
        try:
            return self._container.get_current_slide.execute(self._session_id).label
        except DomainError:
            return "Sin PDF"

    def clarification_state(self) -> tuple[str, str]:
        vista = self._container.get_latest_clarification.execute(self._session_id)
        if not vista or not vista.is_available:
            return "", ""
        return vista.text, vista.clarification_id

    def clarification_text(self) -> str:
        return self.clarification_state()[0]

    def has_clarification(self) -> bool:
        vista = self._container.get_latest_clarification.execute(self._session_id)
        return bool(vista and vista.is_available)

    def session_title(self) -> str:
        sesion = self._container.sessions.get(self._session_id)
        titulo = sesion.title if sesion else ""
        self._titulo_visto = titulo
        return titulo

    def notes_text(self) -> str:
        return self._container.notes.get_or_create(self._session_id).render_raw()

    def drain_announcements(self) -> str:
        hub = getattr(self._container, "live_region", None)
        if hub is None:
            return ""
        return " ".join(n.message for n in hub.drain(self._session_id) if n.message)

    def reset_view_state(self) -> None:
        self.drain_announcements()

    _PAYLOAD_INTERNO = ("'_type': 'gradio.", '"_type": "gradio.', "gradio.FileData")

    def _es_payload_interno(self, texto: str) -> bool:
        return any(marca in (texto or "") for marca in self._PAYLOAD_INTERNO)

    def update_notes(self, texto: str, *, is_keystroke: bool = True):

        if self._es_payload_interno(texto):
            logger.error(
                "Se ha descartado un payload interno de Gradio que iba a guardarse "
                "como apuntes del alumno. Se restaura el contenido real."
            )
            return self.notes_text(), ""

        vista = self._container.update_notes.execute(
            UpdateNotesCommand(
                session_id=self._session_id, text=texto or "", is_keystroke=is_keystroke
            )
        )

        cambiado = bool(vista.restored_markers or vista.inserted_markers)
        return (vista.text if cambiado else None), vista.announcement

    def rename_session(self, titulo: str) -> str:
        limpio = (titulo or "").strip()[:200]
        sesion = self._container.sessions.get(self._session_id)
        if sesion is None or sesion.title == limpio:
            self._titulo_visto = limpio
            return limpio
        vista = self._container.rename_session.execute(
            RenameSessionCommand(session_id=self._session_id, title=limpio)
        )
        self._titulo_visto = vista.title
        return vista.title

    def sync_title(self, titulo: str) -> str | None:

        en_caja = (titulo or "").strip()[:200]
        sesion = self._container.sessions.get(self._session_id)
        almacenado = sesion.title if sesion else ""
        anterior, self._titulo_visto = self._titulo_visto, en_caja

        if almacenado == en_caja:
            return None
        if anterior is not None and en_caja != anterior:

            self.rename_session(en_caja)
            return None

        self._titulo_visto = almacenado
        return almacenado

    def insert_clarification(self):
        vista = self._container.insert_clarification.execute(
            InsertClarificationCommand(session_id=self._session_id, requested_by_student=True)
        )
        return vista.text, (vista.announcement or "No hay ninguna aclaracion que insertar.")

    def listen_clarification(self):

        try:
            salida = self._container.listen_clarification.execute(self._session_id)
        except NoClarificationAvailable as exc:
            return "", str(exc)
        return salida.text, "Reproduciendo la aclaracion."

    def announce_slide(self) -> str:
        notas = self._container.notes.get_or_create(self._session_id)
        actual = notas.current_slide
        donde = (
            f" Estas escribiendo en la diapositiva {actual.number}."
            if actual is not None
            else " Todavia no has escrito nada."
        )
        return f"{self.slide_label()}.{donde}"

    def jump_to_slide(self) -> str:
        return self._container.jump_to_slide_notes.execute(self._session_id).announcement

    def export_url(self, *, processed: bool):

        import urllib.parse

        documento = self._container.export_notes.execute(
            ExportNotesCommand(session_id=self._session_id, fmt="text", processed=processed)
        )
        destino = Path(tempfile.gettempdir()) / documento.filename
        destino.write_bytes(documento.content)
        aviso = (
            f"Apuntes descargados. {documento.disclaimer}"
            if documento.processed
            else "Apuntes descargados tal y como los escribiste, sin procesar."
        )
        url = "/gradio_api/file=" + urllib.parse.quote(str(destino).replace("\\", "/"))

        return f"{time.time_ns()}|{url}", aviso

def _sr(mensaje: str, cortesia: str = "polite") -> str:

    return (
        f'<div id="region-anuncios" role="status" aria-live="{cortesia}" '
        f'aria-atomic="true">{html_lib.escape(mensaje or "")}</div>'
    )

def _bridge_value(valor: str = "") -> str:
    return f'<span data-value="{html_lib.escape(valor or "", quote=True)}"></span>'

def build_student_app(
    container: Container, session_id: SessionId, *, follow_latest: bool = False
):

    import gradio as gr

    ui = StudentUiAdapter(container, session_id, follow_latest=follow_latest)
    atajos = container.settings.accessibility.shortcuts
    conflictos = shortcut_registry.conflicts(atajos)
    if conflictos:
        for enlace in conflictos:
            logger.warning(
                "El atajo %s puede no funcionar: %s Alternativa: %s",
                enlace.combo,
                enlace.conflict.detail,
                enlace.conflict.suggestion,
            )

    with gr.Blocks(title="Cognitive Agent") as demo:
        gr.HTML(
            """
            <header class="student-header">
              <div class="student-header-row">
                <div class="student-brand">
                  <h1 class="student-title">Cognitive Agent</h1>
                </div>
                <div class="student-header-actions">
                  <div class="student-status-pill" aria-hidden="true">Sesión sincronizada</div>
                  <button
                    id="student-settings-btn"
                    class="student-settings-button"
                    type="button"
                    aria-label="Ajustes"
                    title="Ajustes"
                    aria-expanded="false"
                    aria-controls="student-settings-panel"
                  ><span aria-hidden="true">&#9881;</span></button>
                </div>
              </div>
            </header>
            <section
              id="student-settings-panel"
              class="student-settings-panel"
              aria-labelledby="student-settings-title"
              hidden
            >
              <h2 id="student-settings-title" class="student-settings-title">Ajustes</h2>
              <div class="student-setting">
                <label for="student-reading-rate">Velocidad de lectura</label>
                <select id="student-reading-rate">
                  <option value="1">x1</option>
                  <option value="1.5">x1,5</option>
                  <option value="2">x2</option>
                  <option value="3">x3</option>
                </select>
              </div>
              <div class="student-setting">
                <label class="student-setting-toggle" for="student-sound-enabled">
                  <input id="student-sound-enabled" type="checkbox" checked>
                  <span>Aviso sonoro</span>
                </label>
              </div>
            </section>
            """
        )

        gr.Textbox(
            label="Clave de sesión",
            type="password",
            elem_classes=["sr-focus"],
            visible=False,
            show_label=False,
        )
        gr.Button("Conectar", variant="primary", visible=False)

        anuncios = gr.HTML(value=_sr(""), elem_id="contenedor-anuncios")

        with gr.Column(elem_classes=["student-shell"]):
            with gr.Column(elem_classes=["student-panel", "clarification-panel"]):
                btn_announce_slide = gr.Button(
                    "Leer diapositiva",
                    visible=True,
                    variant="secondary",
                    elem_id="announce-slide-btn",
                )
                btn_insert_aclaracion = gr.Button(
                    "Insertar aclaración",
                    visible=True,
                    variant="secondary",
                    elem_id="insert-clar-btn",
                )
                btn_jump_slide_notes = gr.Button(
                    "Ir a notas de esta diapositiva",
                    visible=True,
                    variant="secondary",
                    elem_id="jump-slide-notes-btn",
                )
                gr.HTML(
                    """
                    <div class="panel-title-row">
                      <h2 class="field-heading">Aclaración</h2>
                    </div>
                    """
                )
                output_respuesta = gr.Textbox(
                    label=None,
                    show_label=False,
                    interactive=False,
                    lines=6,
                    elem_id="respuesta-llm",
                    elem_classes=["sr-focus"],
                )
                btn_escuchar = gr.Button(
                    "ESCUCHAR ACLARACIÓN", visible=False, variant="stop", elem_id="escuchar-btn"
                )

                output_session_title = gr.Textbox(
                    label="Título de la sesión",
                    interactive=True,
                    placeholder="Título de la sesión (lo pone el profesor o tú)...",
                    elem_id="titulo-sesion",
                    elem_classes=["sr-focus"],
                    visible=False,
                    show_label=False,
                )
            with gr.Column(elem_classes=["student-panel", "notes-panel"]):
                gr.HTML(
                    """
                    <div class="panel-title-row">
                      <h2 class="field-heading">Notas</h2>
                    </div>
                    """
                )
                output_notas_alumno = gr.Textbox(
                    label=None,
                    show_label=False,
                    interactive=True,
                    lines=16,
                    placeholder="Escribe aquí tus apuntes...",
                    elem_id="notas-alumno",
                    elem_classes=["sr-focus"],
                )

                with gr.Row(elem_classes=["student-actions"]):
                    btn_descargar_notas = gr.Button(
                        "Descargar notas",
                        variant="secondary",
                        elem_id="descargar-notas-btn",
                        elem_classes=["sr-focus"],
                    )
                    btn_descargar_notas_formateadas = gr.Button(
                        "Descargar notas formateadas",
                        variant="secondary",
                        elem_id="descargar-notas-formateadas-btn",
                        elem_classes=["sr-focus"],
                    )
                output_slide_text = gr.HTML(
                    value=_bridge_value("Sin PDF"),
                    elem_id="slide-sync",
                )

        beep_trigger = gr.HTML(value=_bridge_value(""), elem_id="beep-trigger")
        puente_locucion = gr.HTML(value=_bridge_value(""), elem_id="puente-locucion")
        descarga_url = gr.HTML(value=_bridge_value(""), elem_id="descarga-trigger")

        tts_audio = gr.Audio(
            value=None,
            label="Audio asistente",
            autoplay=True,
            interactive=False,
            elem_id="tts-audio",
            show_label=False,
        )

        def on_tick(texto_notas: str, titulo: str):

            if ui.follow_latest_session():
                aclaracion, aclaracion_id = ui.clarification_state()
                return (
                    gr.update(value=ui.notes_text()),
                    _sr("Conectado a la sesion activa mas reciente."),
                    _bridge_value(ui.slide_label()),
                    gr.update(value=aclaracion),
                    gr.update(visible=bool(aclaracion)),
                    _bridge_value(aclaracion_id),
                    gr.update(value=ui.session_title()),
                )

            titulo_nuevo = ui.sync_title(titulo)
            nuevo, aviso = ui.update_notes(texto_notas, is_keystroke=False)
            pendientes = ui.drain_announcements()
            mensaje = " ".join(m for m in (aviso, pendientes) if m)
            aclaracion, aclaracion_id = ui.clarification_state()
            disponible = bool(aclaracion)
            return (
                gr.update(value=nuevo) if nuevo is not None else gr.update(),
                _sr(mensaje) if mensaje else gr.update(),
                _bridge_value(ui.slide_label()),
                aclaracion or gr.update(),
                gr.update(visible=disponible),

                _bridge_value(aclaracion_id) if disponible else gr.update(),
                gr.update(value=titulo_nuevo) if titulo_nuevo is not None else gr.update(),
            )

        def on_notas(texto: str):
            nuevo, aviso = ui.update_notes(texto, is_keystroke=True)
            return (
                gr.update(value=nuevo) if nuevo is not None else gr.update(),
                _sr(aviso, "assertive") if aviso else gr.update(),
            )

        def on_titulo(titulo: str):
            ui.rename_session(titulo)
            return gr.update()

        def on_escuchar():
            import time

            texto, aviso = ui.listen_clarification()

            return (
                _bridge_value(f"{time.time_ns()}|{texto}") if texto else gr.update(),
                _sr(aviso, "assertive"),
            )

        def on_insertar():
            texto, aviso = ui.insert_clarification()
            return (
                gr.update(value=texto) if texto is not None else gr.update(),
                _sr(aviso, "assertive"),
            )

        def on_anunciar():
            return _sr(ui.announce_slide(), "assertive")

        def on_ir():
            return _sr(ui.jump_to_slide(), "assertive")

        def on_descargar_bruto():
            url, aviso = ui.export_url(processed=False)
            return _bridge_value(url), _sr(aviso, "assertive")

        def on_descargar_procesado():
            url, aviso = ui.export_url(processed=True)
            return _bridge_value(url), _sr(aviso, "assertive")

        def on_load():

            ui.reset_view_state()
            return (
                "",
                ui.session_title(),
                _bridge_value(ui.slide_label()),
                "",
                gr.update(visible=False),
                _sr(shortcut_registry.help_text(atajos)),
            )

        output_notas_alumno.change(
            on_notas, inputs=[output_notas_alumno], outputs=[output_notas_alumno, anuncios]
        )
        output_session_title.change(
            on_titulo, inputs=[output_session_title], outputs=[output_session_title]
        )
        btn_escuchar.click(on_escuchar, outputs=[puente_locucion, anuncios])
        btn_insert_aclaracion.click(on_insertar, outputs=[output_notas_alumno, anuncios])
        btn_announce_slide.click(on_anunciar, outputs=[anuncios])
        btn_jump_slide_notes.click(on_ir, outputs=[anuncios])
        btn_descargar_notas.click(
            on_descargar_bruto, outputs=[descarga_url, anuncios]
        )
        btn_descargar_notas_formateadas.click(
            on_descargar_procesado, outputs=[descarga_url, anuncios]
        )

        demo.load(
            on_load,
            outputs=[
                output_notas_alumno,
                output_session_title,
                output_slide_text,
                output_respuesta,
                btn_escuchar,
                anuncios,
            ],
        )

        gr.Timer(1.0).tick(
            on_tick,
            inputs=[output_notas_alumno, output_session_title],
            outputs=[
                output_notas_alumno,
                anuncios,
                output_slide_text,
                output_respuesta,
                btn_escuchar,
                beep_trigger,

                output_session_title,
            ],
        )

        demo.load(fn=None, js=STUDENT_JS)

    demo.cognitive_agent_launch_kwargs = {
        "theme": gr.themes.Soft(),
        "css": STUDENT_CSS,

        "footer_links": [],

        "allowed_paths": [tempfile.gettempdir()],
    }
    return demo

def launch_student_app(demo, **kwargs) -> None:

    opciones = dict(getattr(demo, "cognitive_agent_launch_kwargs", {}))
    opciones.update(kwargs)
    demo.launch(**opciones)
