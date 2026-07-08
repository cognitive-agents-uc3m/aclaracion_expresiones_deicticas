import gradio as gr
from .handlers import (
    actualizar_notas,
    anunciar_diapositiva,
    conectar,
    enviar,
    escuchar,
    insertar_aclaracion,
    refrescar,
)

_KEYBOARD_AND_ACCESSIBILITY_JS = """
() => {
    // AudioContext singleton: se crea en el primer gesto del usuario (requisito del navegador)
    if (!window._beepCtxReady) {
        window._beepCtxReady = true;
        window._beepCtx = null;
        const _initBeepCtx = () => {
            if (!window._beepCtx) {
                try { window._beepCtx = new (window.AudioContext || window.webkitAudioContext)(); }
                catch(e) {}
            }
            if (window._beepCtx && window._beepCtx.state === 'suspended') {
                window._beepCtx.resume().catch(() => {});
            }
        };
        document.addEventListener('click',   _initBeepCtx, true);
        document.addEventListener('keydown', _initBeepCtx, true);
    }

    function playBeep() {
        const ctx = window._beepCtx;
        if (!ctx || ctx.state !== 'running') return;
        try {
            const osc  = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.frequency.value = 880;
            osc.type = 'sine';
            gain.gain.setValueAtTime(0.25, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.18);
            osc.start(ctx.currentTime);
            osc.stop(ctx.currentTime + 0.18);
        } catch(e) {}
    }

    if (!window._beepWatcherStarted) {
        window._beepWatcherStarted = true;
        let _lastBeepVal = "";
        setInterval(() => {
            const root = document.getElementById("beep-trigger");
            if (!root) return;
            const field = root.querySelector("textarea, input");
            if (!field) return;
            if (field.value && field.value !== _lastBeepVal) {
                _lastBeepVal = field.value;
                playBeep();
            }
        }, 300);
    }

    if (!window._announceSlideBound) {
        window._announceSlideBound = true;
        window.addEventListener("keydown", (ev) => {
            if (ev.repeat) return;
            if (ev.key === "F8") {
                ev.preventDefault();
                ev.stopPropagation();
                const btn = document.getElementById("announce-slide-btn");
                if (btn) btn.click();
                return;
            }
            if (ev.key === "F9") {
                ev.preventDefault();
                ev.stopPropagation();
                const btn = document.getElementById("insert-clar-btn");
                if (btn) btn.click();
                return;
            }
            if (ev.key === "F7") {
                ev.preventDefault();
                ev.stopPropagation();
                const btn = document.getElementById("escuchar-btn");
                if (btn) btn.click();
                return;
            }
            if (ev.key === "F2") {
                ev.preventDefault();
                ev.stopPropagation();
                if (window._jumpNotesToCurrentSlide) window._jumpNotesToCurrentSlide();
                return;
            }
        }, true);
    }

    const getField = (id) => {
        const root = document.getElementById(id);
        if (!root) return null;
        return root.querySelector("textarea, input");
    };

    const jumpNotesToCurrentSlide = () => {
        const slideField = getField("slide-sync");
        const notesField = getField("notas-alumno");
        if (!slideField || !notesField) return;

        const slideText = (slideField.value || "").trim();
        const m = slideText.match(/Diapositiva\\s+(\\d+)\\s*\\/\\s*(\\d+)/i);
        if (!m) return;
        const slideNumber = parseInt(m[1], 10);
        if (!Number.isFinite(slideNumber) || slideNumber <= 0) return;

        const marker = `[Diapositiva ${slideNumber}]`;
        let text = (notesField.value || "").replace(/\\r\\n/g, "\\n").replace(/\\r/g, "\\n");

        let markerIdx = text.lastIndexOf(marker);
        if (markerIdx < 0) {
            const base = text.replace(/\\s+$/, "");
            const sep = base ? "\\n\\n" : "";
            text = `${base}${sep}${marker}\\n`;
            notesField.value = text;
            markerIdx = (base + sep).length;
        }

        const afterMarker = markerIdx + marker.length;
        let nextMarkerIdx = text.indexOf("[Diapositiva ", afterMarker);
        if (nextMarkerIdx < 0) nextMarkerIdx = text.length;

        const blockText = text.slice(0, nextMarkerIdx);
        let caret = blockText.replace(/\\s+$/, "").length;
        if (caret > 0 && text[caret - 1] !== "\\n") {
            text = text.slice(0, caret) + "\\n" + text.slice(caret);
            notesField.value = text;
            caret += 1;
        }

        notesField.focus();
        notesField.setSelectionRange(caret, caret);

        const before = text.slice(0, caret);
        const lineCount = (before.match(/\\n/g) || []).length;
        const style = window.getComputedStyle(notesField);
        const lineHeight = parseFloat(style.lineHeight) || 18;
        notesField.scrollTop = Math.max(0, (lineCount - 3) * lineHeight);
    };
    window._jumpNotesToCurrentSlide = jumpNotesToCurrentSlide;

    const bindJumpButton = () => {
        const root = document.getElementById("jump-slide-notes-btn");
        if (!root) return false;
        const btn = root.querySelector("button") || root;
        if (!btn || btn.dataset.jumpBound === "1") return true;
        btn.dataset.jumpBound = "1";
        btn.addEventListener("click", (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            if (window._jumpNotesToCurrentSlide) window._jumpNotesToCurrentSlide();
        }, true);
        return true;
    };
    if (!bindJumpButton()) {
        window.setTimeout(bindJumpButton, 300);
        window.setTimeout(bindJumpButton, 1200);
    }

    const makeReadOnlyFocusable = (id) => {
        const root = document.getElementById(id);
        if (!root) return;
        const field = root.querySelector("textarea, input");
        if (!field) return;
        field.readOnly = true;
        field.setAttribute("aria-readonly", "true");
        field.setAttribute("tabindex", "0");
    };
    const setLive = (id, politeness = "polite") => {
        const root = document.getElementById(id);
        if (!root) return;
        const field = root.querySelector("textarea, input");
        if (!field) return;
        field.setAttribute("aria-live", politeness);
        field.setAttribute("role", "status");
        field.setAttribute("aria-atomic", "true");
    };
    makeReadOnlyFocusable("estado-conexion");
    makeReadOnlyFocusable("slide-sync");
    makeReadOnlyFocusable("estado-remoto");
    makeReadOnlyFocusable("estado-pdf-final");
    makeReadOnlyFocusable("estado-pdf-notas");
    makeReadOnlyFocusable("estado-formateo-notas");
    makeReadOnlyFocusable("precompute-local");
    makeReadOnlyFocusable("respuesta-llm");
    makeReadOnlyFocusable("analisis-router");
    makeReadOnlyFocusable("debug-log");
    setLive("respuesta-llm", "assertive");
    setLive("estado-conexion", "polite");
    setLive("estado-remoto", "polite");
    setLive("estado-pdf-final", "polite");
    setLive("estado-pdf-notas", "polite");
    setLive("estado-formateo-notas", "polite");
    setLive("analisis-router", "polite");
    setLive("debug-log", "polite");
}
"""

_CSS = """
textarea[readonly] { user-select: text !important; }
#announce-slide-btn { position: absolute !important; left: -10000px !important; top: auto !important; width: 1px !important; height: 1px !important; overflow: hidden !important; }
#insert-clar-btn    { position: absolute !important; left: -10000px !important; top: auto !important; width: 1px !important; height: 1px !important; overflow: hidden !important; }
#jump-slide-notes-btn { position: absolute !important; left: -10000px !important; top: auto !important; width: 1px !important; height: 1px !important; overflow: hidden !important; }
#slide-sync         { position: absolute !important; left: -10000px !important; top: auto !important; width: 1px !important; height: 1px !important; overflow: hidden !important; }
.sr-focus :focus-visible { outline: 3px solid #1a73e8 !important; outline-offset: 2px !important; }
"""

_CONNECT_OUTPUTS = [
    "sync_state", "runtime_state", "output_conexion",
    "output_slide_text", "output_slide_preview", "output_estado_remoto",
    "output_precompute_local", "output_final_pdf", "output_notes_pdf",
    "output_notes_format", "output_debug_log", "output_router",
    "output_respuesta", "output_notas_alumno", "btn_escuchar",
]

def build_demo() -> gr.Blocks:
    with gr.Blocks(theme=gr.themes.Soft(), css=_CSS) as demo:
        sync_state = gr.State(value=None)
        runtime_state = gr.State(value=None)

        gr.Markdown("# Cognitive Agent")
        session_key = gr.Textbox(
            label="Clave de sesión",
            type="password",
            elem_classes=["sr-focus"],
            visible=False,
        )
        btn_conectar = gr.Button("Conectar", variant="primary", visible=False)

        with gr.Row():
            with gr.Column(scale=1):
                btn_escuchar = gr.Button("OÍR RESPUESTA", visible=False, variant="stop", elem_id="escuchar-btn")
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
                output_respuesta = gr.Textbox(
                    label="Respuesta",
                    interactive=True,
                    lines=6,
                    elem_id="respuesta-llm",
                    elem_classes=["sr-focus"],
                )
                output_notas_alumno = gr.Textbox(
                    label="Notas del alumno",
                    interactive=True,
                    lines=16,
                    placeholder="Escribe aquí tus apuntes...",
                    elem_id="notas-alumno",
                    elem_classes=["sr-focus"],
                )
                output_slide_text = gr.Textbox(
                    label="Diapositiva sincronizada",
                    interactive=True,
                    value="Sin PDF",
                    elem_id="slide-sync",
                    elem_classes=["sr-focus"],
                    visible=True,
                )

        with gr.Accordion(label="Detalles de estado", open=False):
            with gr.Row():
                with gr.Column(scale=1):
                    output_slide_preview = gr.Image(
                        label="Vista previa local",
                        type="filepath",
                        interactive=False,
                        height=340,
                    )
                    output_estado_remoto = gr.Textbox(
                        label="Estado remoto profesor",
                        interactive=True,
                        elem_id="estado-remoto",
                        elem_classes=["sr-focus"],
                    )
                    output_final_pdf = gr.Textbox(
                        label="Estado PDF final",
                        interactive=True,
                        elem_id="estado-pdf-final",
                        elem_classes=["sr-focus"],
                    )
                    output_notes_pdf = gr.Textbox(
                        label="Estado PDF notas alumno",
                        interactive=True,
                        elem_id="estado-pdf-notas",
                        elem_classes=["sr-focus"],
                    )
                    output_notes_format = gr.Textbox(
                        label="Estado formateo notas",
                        interactive=True,
                        elem_id="estado-formateo-notas",
                        elem_classes=["sr-focus"],
                    )
                    output_precompute_local = gr.Textbox(
                        label="Preproceso local alumno",
                        interactive=True,
                        elem_id="precompute-local",
                        elem_classes=["sr-focus"],
                    )
                with gr.Column(scale=1):
                    output_conexion = gr.Textbox(
                        label="Estado conexión",
                        interactive=True,
                        elem_id="estado-conexion",
                        elem_classes=["sr-focus"],
                    )
                    output_router = gr.Textbox(
                        label="Análisis",
                        interactive=True,
                        lines=6,
                        elem_id="analisis-router",
                        elem_classes=["sr-focus"],
                    )
                    output_debug_log = gr.Textbox(
                        label="Log interno",
                        interactive=True,
                        lines=8,
                        elem_id="debug-log",
                        elem_classes=["sr-focus"],
                    )

        beep_trigger = gr.Textbox(value="", visible=False, elem_id="beep-trigger", interactive=False)

        _connect_outputs = [
            sync_state, runtime_state, output_conexion,
            output_slide_text, output_slide_preview, output_estado_remoto,
            output_precompute_local, output_final_pdf, output_notes_pdf,
            output_notes_format, output_debug_log, output_router,
            output_respuesta, output_notas_alumno, btn_escuchar,
        ]
        _connect_inputs = [sync_state, runtime_state, session_key]

        btn_conectar.click(fn=conectar, inputs=_connect_inputs, outputs=_connect_outputs)
        demo.load(fn=conectar, inputs=_connect_inputs, outputs=_connect_outputs)

        btn_escuchar.click(
            fn=escuchar,
            inputs=[runtime_state],
            outputs=[runtime_state, output_respuesta, btn_escuchar],
        )
        btn_announce_slide.click(
            fn=anunciar_diapositiva,
            inputs=[sync_state, runtime_state],
            outputs=[sync_state, runtime_state],
        )
        btn_insert_aclaracion.click(
            fn=insertar_aclaracion,
            inputs=[sync_state, runtime_state, output_notas_alumno],
            outputs=[sync_state, output_notas_alumno],
        )

        timer = gr.Timer(1.0)
        timer.tick(
            fn=refrescar,
            inputs=[sync_state, runtime_state, output_notas_alumno],
            outputs=[
                sync_state, runtime_state, output_conexion,
                output_slide_text, output_slide_preview, output_estado_remoto,
                output_precompute_local, output_final_pdf, output_notes_pdf,
                output_notes_format, output_debug_log, output_router,
                output_respuesta, output_notas_alumno, btn_escuchar,
                beep_trigger,
            ],
        )

        demo.load(fn=None, js=_KEYBOARD_AND_ACCESSIBILITY_JS)

    return demo