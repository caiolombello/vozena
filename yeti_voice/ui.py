"""Native controls for the local Yeti voice processor."""

from collections.abc import Callable
from dataclasses import replace
import math
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QSignalBlocker, QTimer
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .calibration import analyze_voice_sample
from .processing import OUTPUT_NODE
from .settings import PRESETS, Preferences, Settings


class _ScrollSafeComboBox(QComboBox):
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class _ScrollSafeSlider(QSlider):
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class MainWindow(QMainWindow):
    """Main window driven by a VoiceController-compatible QObject."""

    def __init__(
        self,
        controller,
        settings: Settings,
        save_settings: Callable[[Settings], None],
        voice_test=None,
        *,
        preferences: Preferences | None = None,
        save_preferences: Callable[[Preferences], None] | None = None,
    ):
        super().__init__()
        self._controller = controller
        self._settings = settings
        self._save_settings = save_settings
        self._preferences = preferences or Preferences()
        self._save_preferences = save_preferences or (lambda _preferences: None)
        self._consumers = list(getattr(controller, "consumers", []))
        self._processed_is_default = bool(getattr(controller, "is_default_source", False))
        self._configured_source = str(getattr(controller, "configured_default_source", ""))
        self._voice_test = voice_test
        self._voice_state = "idle"
        self._voice_has_clip = False
        self._voice_action = None
        self._calibrating = False
        self._calibration_starting = False
        self._calibration_result = None
        self._calibration_applied = False
        self._running = bool(controller.running)
        self._has_active_contract = hasattr(controller, "active_changed")
        self._active = bool(getattr(controller, "active", self._running))
        self._muted = bool(getattr(controller, "muted", False))
        self._device_connected = bool(controller.device_description)
        self._status_text = ""

        self.setWindowTitle("Vozena")
        self.setMinimumSize(680, 600)
        self.resize(900, 780)
        self._build_ui()
        self._apply_theme()

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(150)
        self._update_timer.timeout.connect(self._commit_settings)

        controller.status_changed.connect(self._set_status)
        controller.running_changed.connect(self._set_running)
        controller.level_changed.connect(self._set_level)
        controller.device_changed.connect(self._set_device)
        controller.error_occurred.connect(self._show_error)
        if self._has_active_contract:
            controller.active_changed.connect(self._set_active)
        if hasattr(controller, "muted_changed"):
            controller.muted_changed.connect(self._set_muted)
        if hasattr(controller, "consumers_changed"):
            controller.consumers_changed.connect(self._set_consumers)
        if hasattr(controller, "default_source_changed"):
            controller.default_source_changed.connect(self._set_default_source)
        if voice_test is not None:
            voice_test.state_changed.connect(self._set_voice_state)
            voice_test.progress_changed.connect(self._set_voice_progress)
            voice_test.clip_changed.connect(self._set_voice_clip)
            voice_test.error_occurred.connect(self._voice_error)

        self._load_settings(settings)
        self._set_device(controller.device_description)
        self._set_status("Pronto para ativar" if controller.device_description else "Conecte o Blue Yeti")
        self._set_active(self._active)
        self._set_running(self._running)
        self._set_muted(self._muted)
        if voice_test is not None:
            self._set_voice_clip(voice_test.has_clip)
            self._set_voice_state(voice_test.state)
            self._set_voice_progress(0)
        self._update_meter_demand()

    def _update_meter_demand(self):
        set_wanted = getattr(self._controller, "set_meter_wanted", None)
        if set_wanted is not None:
            set_wanted(self.isVisible() and not self.isMinimized())

    def showEvent(self, event):
        super().showEvent(event)
        self._update_meter_demand()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._update_meter_demand()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._update_meter_demand()

    @staticmethod
    def _label(text, role="help"):
        label = QLabel(text)
        label.setObjectName(role)
        label.setWordWrap(True)
        return label

    @staticmethod
    def _card(role="card"):
        card = QFrame()
        card.setObjectName(role)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        return card, layout

    def _tab_page(self, title):
        scroll = QScrollArea()
        scroll.setObjectName("tabScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        surface = QWidget()
        surface.setObjectName("pageSurface")
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(14)
        scroll.setWidget(surface)
        self.pages.addTab(scroll, title)
        return layout

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        page = QVBoxLayout(root)
        page.setContentsMargins(24, 20, 24, 14)
        page.setSpacing(14)

        self.brand = QWidget()
        brand = QHBoxLayout(self.brand)
        brand.setContentsMargins(0, 0, 0, 0)
        wordmark = QLabel()
        wordmark.setPixmap(QIcon(str(Path(__file__).resolve().parent.parent / "assets/vozena.svg")).pixmap(42, 42))
        wordmark.setAccessibleName("Vozena")
        wordmark.setObjectName("wordmark")
        wordmark.setFixedSize(42, 42)
        wordmark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.addWidget(wordmark)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(self._label("Vozena", "title"))
        titles.addWidget(self._label("Sua voz, pronta para a reunião", "subtitle"))
        brand.addLayout(titles, 1)
        brand.addWidget(self._label("ÁUDIO LOCAL", "eyebrow"))
        page.addWidget(self.brand)

        self.session_header, session = self._card("sessionHeader")
        session.setContentsMargins(18, 14, 18, 16)
        session.setSpacing(9)
        status_top = QHBoxLayout()
        self.state_dot = QLabel("●")
        self.state_dot.setObjectName("stateDot")
        self.device_label = self._label("", "deviceLabel")
        status_top.addWidget(self.state_dot)
        status_top.addWidget(self.device_label, 1)
        self.state_label = QLabel("Pausado")
        self.state_label.setObjectName("stateLabel")
        status_top.addWidget(self.state_label)
        session.addLayout(status_top)
        self.status_label = self._label("Pronto para ativar", "sessionStatus")
        session.addWidget(self.status_label)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.start_button = QPushButton("Ativar tratamento")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setMinimumHeight(42)
        self.start_button.setAccessibleName("Ativar ou parar o tratamento de voz")
        self.start_button.clicked.connect(self._toggle_running)
        self.mute_button = QPushButton("Silenciar")
        self.mute_button.setObjectName("muteButton")
        self.mute_button.setMinimumHeight(42)
        self.mute_button.setMinimumWidth(176)
        self.mute_button.setCheckable(True)
        self.mute_button.setToolTip("Silencia somente a entrada Yeti Processado usada na reunião")
        self.mute_button.toggled.connect(self._controller.set_mute)
        actions.addWidget(self.start_button, 1)
        actions.addWidget(self.mute_button)
        session.addLayout(actions)
        page.addWidget(self.session_header)

        self.error_banner, error_row = self._card("errorBanner")
        error_row.setContentsMargins(14, 10, 14, 10)
        error_line = QHBoxLayout()
        self.error_label = self._label("", "error")
        self.error_label.setAccessibleName("Aviso do Vozena")
        self.error_label.hide()
        self.dismiss_error_button = QPushButton("Fechar aviso")
        self.dismiss_error_button.setObjectName("quietButton")
        self.dismiss_error_button.clicked.connect(self._dismiss_error)
        error_line.addWidget(self.error_label, 1)
        error_line.addWidget(self.dismiss_error_button)
        error_row.addLayout(error_line)
        self.error_banner.hide()
        page.addWidget(self.error_banner)

        self.activity_card, activity = self._card("activityCard")
        activity.setContentsMargins(14, 10, 14, 10)
        activity_line = QHBoxLayout()
        self.activity_status_label = self._label("", "sectionLabel")
        self.activity_cancel_button = QPushButton("Cancelar gravação")
        self.activity_cancel_button.clicked.connect(self._cancel_voice_test)
        activity_line.addWidget(self.activity_status_label, 1)
        activity_line.addWidget(self.activity_cancel_button)
        activity.addLayout(activity_line)
        self.activity_card.hide()
        page.addWidget(self.activity_card)

        self.pages = QTabWidget()
        self.pages.setObjectName("pages")
        self.pages.setAccessibleName("Tarefas do Vozena")
        self.pages.setDocumentMode(True)
        self.pages.tabBar().setDrawBase(False)
        page.addWidget(self.pages, 1)
        self._build_microphone(self._tab_page("Microfone"))
        if self._voice_test is not None:
            calibration_page = self._tab_page("Calibrar")
            comparison_page = self._tab_page("Comparar áudio")
            self._build_voice_test(comparison_page)
            self._build_calibration(calibration_page)

        footer = QHBoxLayout()
        self.shortcut_label = self._label("Atalho global: verificando…", "footer")
        self.shortcut_label.setToolTip("O atalho alterna o silêncio do Yeti Processado mesmo com outra janela em foco")
        footer.addWidget(self.shortcut_label, 1)
        self.tray_help = self._label("Fechar janela", "footer")
        footer.addWidget(self.tray_help)
        page.addLayout(footer)

    def _build_microphone(self, page):
        destination = QFrame()
        destination.setObjectName("destinationCard")
        row = QHBoxLayout(destination)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(12)
        route = QVBoxLayout()
        route.setSpacing(2)
        route.addWidget(self._label("NA SUA REUNIÃO", "eyebrow"))
        self.destination_card = destination
        self.destination_title = self._label("Selecione Yeti Processado como microfone", "destination")
        self.destination_title.setAccessibleName("Uso do Yeti Processado")
        route.addWidget(self.destination_title)
        self.destination_detail = self._label("", "destinationDetail")
        route.addWidget(self.destination_detail)
        row.addLayout(route, 1)
        self.default_source_button = QPushButton("Usar como microfone padrão")
        self.default_source_button.setObjectName("quietButton")
        self.default_source_button.setToolTip(
            "Faz os apps que usam o microfone padrão do sistema receberem sua voz tratada")
        self.default_source_button.clicked.connect(self._toggle_default_source)
        self.default_source_button.setVisible(hasattr(self._controller, "set_default_source"))
        row.addWidget(self.default_source_button, 0, Qt.AlignmentFlag.AlignVCenter)
        page.addWidget(destination)

        controls_card, controls = self._card()
        preset_row = QHBoxLayout()
        preset_label = QLabel("Perfil de voz")
        preset_label.setObjectName("sectionLabel")
        self.preset_combo = _ScrollSafeComboBox()
        self.preset_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.preset_combo.setObjectName("presetCombo")
        self.preset_combo.addItems([*PRESETS, "Personalizado"])
        self.preset_combo.setAccessibleName("Perfil de voz")
        self.preset_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.preset_combo.currentTextChanged.connect(self._preset_changed)
        preset_label.setBuddy(self.preset_combo)
        preset_row.addWidget(preset_label)
        preset_row.addStretch()
        preset_row.addWidget(self.preset_combo, 1)
        controls.addLayout(preset_row)
        self.noise_slider, self.noise_value = self._add_slider(
            controls, "Redução de ruído", "Suaviza sons constantes do ambiente", 0, 100, "noiseSlider")
        self.clarity_slider, self.clarity_value = self._add_slider(
            controls, "Clareza da voz", "Dá mais presença e definição à fala", 0, 100, "claritySlider")
        self.gain_slider, self.gain_value = self._add_slider(
            controls, "Volume da voz", "Mais baixo  ←  Neutro  →  Mais alto", -24, 12, "gainSlider")
        self.gain_slider.setAccessibleDescription("Ganho de menos 12 a mais 6 decibéis. Cada passo ajusta meio decibel.")
        self.noise_slider.valueChanged.connect(self._controls_changed)
        self.clarity_slider.valueChanged.connect(self._controls_changed)
        self.gain_slider.valueChanged.connect(self._controls_changed)

        meter_card, meter = self._card()
        meter.setContentsMargins(20, 14, 20, 14)
        meter_top = QHBoxLayout()
        meter_top.addWidget(self._label("Nível da sua voz", "sectionLabel"))
        self.level_status_label = QLabel("Sem leitura")
        self.level_status_label.setObjectName("levelStatus")
        meter_top.addStretch()
        self.level_label = QLabel("— dBFS")
        self.level_label.setObjectName("technical")
        meter_top.addWidget(self.level_label)
        meter.addLayout(meter_top)
        meter.addWidget(self.level_status_label)
        self.level_meter = QProgressBar()
        self.level_meter.setObjectName("levelMeter")
        self.level_meter.setAccessibleName("Nível de saída do Yeti Processado")
        self.level_meter.setRange(0, 600)
        self.level_meter.setValue(0)
        self.level_meter.setTextVisible(False)
        meter.addWidget(self.level_meter)
        self.saturation_label = self._label("Pico muito alto — reduza o volume da voz", "warning")
        self.saturation_label.hide()
        meter.addWidget(self.saturation_label)
        self.meter_help = self._label("Ative o tratamento para acompanhar sua voz.")
        meter.addWidget(self.meter_help)

        signal_card, signal_layout = self._card()
        signal_layout.setContentsMargins(20, 14, 20, 14)
        signal_layout.addWidget(self._label("Sinal enviado à reunião", "sectionLabel"))
        signal_row = QHBoxLayout()
        self.processed_button = QPushButton("Tratado")
        self.processed_button.setCheckable(True)
        self.processed_button.setChecked(True)
        self.processed_button.setObjectName("modeButton")
        self.processed_button.clicked.connect(lambda: self._set_bypass(False))
        self.original_button = QPushButton("Original")
        self.original_button.setCheckable(True)
        self.original_button.setObjectName("modeButton")
        self.original_button.clicked.connect(lambda: self._set_bypass(True))
        self.signal_group = QButtonGroup(self)
        self.signal_group.setExclusive(True)
        self.signal_group.addButton(self.processed_button)
        self.signal_group.addButton(self.original_button)
        signal_row.addWidget(self.processed_button, 1)
        signal_row.addWidget(self.original_button, 1)
        signal_layout.addLayout(signal_row)
        self.signal_help = self._label("O sinal tratado usa seus ajustes de ruído, clareza e volume.")
        signal_layout.addWidget(self.signal_help)
        body = QWidget()
        body.setObjectName("pageSurface")
        self._microphone_grid = QGridLayout(body)
        self._microphone_grid.setContentsMargins(0, 0, 0, 0)
        self._microphone_grid.setSpacing(14)
        self._microphone_cards = (controls_card, meter_card, signal_card)
        self._microphone_wide = None
        page.addWidget(body)
        self._layout_microphone()
        page.addStretch()

    def _layout_microphone(self):
        wide = self.width() >= 840
        if wide == self._microphone_wide:
            return
        self._microphone_wide = wide
        grid = self._microphone_grid
        for card in self._microphone_cards:
            grid.removeWidget(card)
        controls, meter, signal = self._microphone_cards
        if wide:
            grid.addWidget(controls, 0, 0, 2, 1)
            grid.addWidget(meter, 0, 1)
            grid.addWidget(signal, 1, 1)
        else:
            for row, card in enumerate(self._microphone_cards):
                grid.addWidget(card, row, 0)
        grid.setColumnStretch(0, 3 if wide else 1)
        grid.setColumnStretch(1, 2 if wide else 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "brand"):
            self.brand.setVisible(self.height() > 660)
        if hasattr(self, "_microphone_grid"):
            self._layout_microphone()
        if (hasattr(self, "calibration_result_card") and self.pages.currentIndex() == 1
                and not self.calibration_result_card.isHidden()):
            QTimer.singleShot(0, self._reveal_calibration_result)

    def _build_voice_test(self, page):
        page.addWidget(self._label("Ouça a diferença", "pageTitle"))
        page.addWidget(self._label("Grave uma frase de 10 segundos e compare a mesma amostra com e sem tratamento.", "intro"))
        card, layout = self._card()
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(10)
        header = QHBoxLayout()
        self.voice_status_label = self._label("Pronto para gravar", "sectionLabel")
        self.voice_time_label = QLabel("—")
        self.voice_time_label.setObjectName("sliderValue")
        header.addWidget(self.voice_status_label, 1)
        header.addWidget(self.voice_time_label)
        layout.addLayout(header)
        self.voice_progress = QProgressBar()
        self.voice_progress.setObjectName("voiceProgress")
        self.voice_progress.setAccessibleName("Progresso da amostra de voz")
        self.voice_progress.setRange(0, 100)
        self.voice_progress.setTextVisible(False)
        layout.addWidget(self.voice_progress)
        recording = QHBoxLayout()
        self.voice_record_button = QPushButton("Gravar 10 s")
        self.voice_record_button.setObjectName("primaryButton")
        self.voice_record_button.clicked.connect(self._record_voice_test)
        self.voice_cancel_button = QPushButton("Cancelar")
        self.voice_cancel_button.clicked.connect(self._cancel_voice_test)
        self.voice_clear_button = QPushButton("Descartar amostra")
        self.voice_clear_button.setObjectName("quietButton")
        self.voice_clear_button.clicked.connect(self._clear_voice_test)
        recording.addWidget(self.voice_record_button)
        recording.addWidget(self.voice_cancel_button)
        recording.addStretch()
        recording.addWidget(self.voice_clear_button)
        layout.addLayout(recording)
        layout.addWidget(self._label("Use fones de ouvido. Fale como você falaria em uma reunião."))
        page.addWidget(card)

        listening, listen = self._card()
        listen.setContentsMargins(20, 14, 20, 14)
        listen.setSpacing(10)
        listen.addWidget(self._label("Compare sua amostra", "sectionLabel"))
        self.voice_listening_help = self._label("A comparação fica disponível depois da gravação.")
        listen.addWidget(self.voice_listening_help)
        listen_buttons = QHBoxLayout()
        self.voice_original_button = QPushButton("Ouvir original")
        self.voice_original_button.clicked.connect(lambda: self._play_voice_test("original"))
        self.voice_processed_button = QPushButton("Ouvir tratado")
        self.voice_processed_button.clicked.connect(lambda: self._play_voice_test("processed"))
        listen_buttons.addWidget(self.voice_original_button, 1)
        listen_buttons.addWidget(self.voice_processed_button, 1)
        listen.addLayout(listen_buttons)
        self.voice_snapshot_label = self._label("Amostra usa os ajustes do momento da gravação", "snapshot")
        self.voice_snapshot_label.hide()
        listen.addWidget(self.voice_snapshot_label)
        page.addWidget(listening)
        page.addWidget(self._label("O áudio fica apenas na memória desta sessão. Você pode descartá-lo ou encerrar o app para apagá-lo.", "privacy"))
        page.addStretch()

    def _build_calibration(self, page):
        page.addWidget(self._label("Encontre um bom ponto de partida", "pageTitle"))
        page.addWidget(self._label("Em 10 segundos, medimos seu ambiente e o volume da sua voz. Você decide se quer aplicar a sugestão.", "intro"))
        steps = QHBoxLayout()
        self.calibration_steps = []
        for text, detail in (("1 · Ambiente", "3 s em silêncio"), ("2 · Sua voz", "7 s falando normalmente")):
            card, step = self._card("stepCard")
            step.addWidget(self._label(text, "sectionLabel"))
            step.addWidget(self._label(detail))
            self.calibration_steps.append(card)
            steps.addWidget(card, 1)
        page.addLayout(steps)

        recording, capture = self._card()
        self.calibration_instruction = self._label("Tudo pronto para começar?", "instruction")
        capture.addWidget(self.calibration_instruction)
        capture.addWidget(self._label("Mantenha o microfone na posição que você usa nas chamadas."))
        self.calibration_progress = QProgressBar()
        self.calibration_progress.setObjectName("voiceProgress")
        self.calibration_progress.setAccessibleName("Progresso da calibração guiada")
        self.calibration_progress.setRange(0, 100)
        self.calibration_progress.setValue(0)
        self.calibration_progress.setTextVisible(False)
        capture.addWidget(self.calibration_progress)
        actions = QHBoxLayout()
        self.calibration_button = QPushButton("Começar calibração · 10 s")
        self.calibration_button.setObjectName("primaryButton")
        self.calibration_button.clicked.connect(self._start_calibration)
        self.calibration_cancel_button = QPushButton("Cancelar")
        self.calibration_cancel_button.clicked.connect(self._cancel_voice_test)
        self.calibration_compare_button = QPushButton("Ouvir a amostra")
        self.calibration_compare_button.clicked.connect(lambda: self.pages.setCurrentIndex(2))
        self.calibration_compare_button.hide()
        actions.addWidget(self.calibration_button, 1)
        actions.addWidget(self.calibration_cancel_button)
        actions.addWidget(self.calibration_compare_button)
        capture.addLayout(actions)
        self.calibration_status_label = self._label("Nenhum ajuste será aplicado automaticamente.", "help")
        capture.addWidget(self.calibration_status_label)
        page.addWidget(recording)

        self.calibration_result_card, result = self._card("resultCard")
        self.calibration_result_title = self._label("Ajustes sugeridos", "sectionLabel")
        result.addWidget(self.calibration_result_title)
        self.calibration_changes_label = self._label("", "resultValue")
        result.addWidget(self.calibration_changes_label)
        self.calibration_apply_button = QPushButton("Aplicar ajustes")
        self.calibration_apply_button.setObjectName("primaryButton")
        self.calibration_apply_button.setEnabled(False)
        self.calibration_apply_button.clicked.connect(self._apply_calibration)
        result.addWidget(self.calibration_apply_button)
        self.calibration_details_button = QPushButton("Detalhes da medição")
        self.calibration_details_button.setObjectName("quietButton")
        self.calibration_details_button.setCheckable(True)
        self.calibration_metrics_label = self._label("", "technical")
        self.calibration_metrics_label.hide()
        self.calibration_details_button.toggled.connect(self.calibration_metrics_label.setVisible)
        result.addWidget(self.calibration_details_button)
        result.addWidget(self.calibration_metrics_label)
        self.calibration_result_card.hide()
        page.addWidget(self.calibration_result_card)
        page.addStretch()

    @staticmethod
    def _add_slider(layout, title, description, minimum, maximum, object_name):
        block = QVBoxLayout()
        block.setSpacing(5)
        top = QHBoxLayout()
        label = QLabel(title)
        label.setObjectName("controlLabel")
        value = QLabel()
        value.setObjectName("sliderValue")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(label, 1)
        top.addWidget(value)
        block.addLayout(top)
        slider = _ScrollSafeSlider(Qt.Orientation.Horizontal)
        slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        slider.setObjectName(object_name)
        slider.setRange(minimum, maximum)
        slider.setAccessibleName(title)
        slider.setAccessibleDescription(description)
        slider.setToolTip(description)
        slider.setSingleStep(1)
        slider.setPageStep(10 if minimum == 0 else 2)
        label.setBuddy(slider)
        block.addWidget(slider)
        helper = QLabel(description)
        helper.setObjectName("controlHelp")
        helper.setWordWrap(True)
        block.addWidget(helper)
        layout.addLayout(block)
        return slider, value

    def _load_settings(self, settings: Settings):
        with (
            QSignalBlocker(self.noise_slider),
            QSignalBlocker(self.clarity_slider),
            QSignalBlocker(self.gain_slider),
        ):
            self.noise_slider.setValue(settings.noise)
            self.clarity_slider.setValue(settings.clarity)
            self.gain_slider.setValue(round(settings.gain_db * 2))
        self._settings = settings
        self._update_value_labels()
        self._sync_preset_name()

    def _settings_from_controls(self):
        return Settings(
            noise=self.noise_slider.value(),
            clarity=self.clarity_slider.value(),
            gain_db=self.gain_slider.value() / 2,
        )

    def _controls_changed(self):
        self._settings = self._settings_from_controls()
        self._update_value_labels()
        self._sync_preset_name()
        self._update_timer.start()

    def _preset_changed(self, name):
        if name not in PRESETS:
            return
        self._load_settings(PRESETS[name])
        self._update_timer.start()

    def _sync_preset_name(self):
        name = next(
            (name for name, values in PRESETS.items() if values == self._settings),
            "Personalizado",
        )
        with QSignalBlocker(self.preset_combo):
            self.preset_combo.setCurrentText(name)

    def _update_value_labels(self):
        self.noise_value.setText(f"{self.noise_slider.value()}%")
        self.clarity_value.setText(f"{self.clarity_slider.value()}%")
        gain = self.gain_slider.value() / 2
        direction = "Neutro" if gain == 0 else "Mais baixo" if gain < 0 else "Mais alto"
        self.gain_value.setText(f"{direction} · {gain:+.1f} dB")

    def _commit_settings(self):
        self._save_settings(self._settings)
        self._controller.update_settings(self._settings)

    def _toggle_running(self):
        if self._active:
            self._controller.stop()
        else:
            self._controller.start(self._settings)

    def _set_bypass(self, bypass):
        with (
            QSignalBlocker(self.original_button),
            QSignalBlocker(self.processed_button),
        ):
            self.original_button.setChecked(bypass)
            self.processed_button.setChecked(not bypass)
        self._controller.set_bypass(bypass)
        self.signal_help.setText(
            "O sinal original envia a voz sem os ajustes. A comparação afeta a entrada da reunião."
            if bypass else "O sinal tratado usa seus ajustes de ruído, clareza e volume."
        )

    def _set_running(self, running):
        self._running = bool(running)
        if not self._has_active_contract:
            self._active = self._running
        self._refresh_engine_state()
        if not self._running:
            self._reset_meter()

    def _set_active(self, active):
        self._active = bool(active)
        self._refresh_engine_state()

    def _set_muted(self, muted):
        self._muted = bool(muted)
        with QSignalBlocker(self.mute_button):
            self.mute_button.setChecked(self._muted)
        self.mute_button.setText("Reativar microfone" if self._muted else "Silenciar")
        self.mute_button.setAccessibleName(self.mute_button.text())
        self._refresh_engine_state()
        self._reset_meter()

    def _refresh_engine_state(self):
        self._refresh_destination()
        if self._running and self._muted:
            label, tone = "Silenciado", "muted"
        elif self._running:
            label, tone = "Ativo", "active"
        elif self._active:
            label = "Preparando…" if "preparando" in self._status_text.lower() else "Reconectando…"
            tone = "waiting"
        else:
            label, tone = "Pausado", "paused"
        self.state_label.setText(label)
        for widget in (self.session_header, self.state_label, self.state_dot):
            widget.setProperty("tone", tone)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.start_button.setProperty("sessionActive", self._active)
        self.start_button.style().unpolish(self.start_button)
        self.start_button.style().polish(self.start_button)
        self.start_button.setText(
            "Parar tratamento" if self._active else "Ativar tratamento"
        )
        for button in (self.original_button, self.processed_button):
            button.setEnabled(self._running)
        self.mute_button.setEnabled(self._active)
        if self._running and self._muted:
            text = "Yeti Processado está sem áudio. Reative o microfone quando quiser falar."
        elif not self._device_connected and not self._active:
            text = "Conecte o Blue Yeti por USB para começar."
        else:
            text = self._status_text or "Pronto para ativar"
        self.status_label.setText(text)

    def _set_consumers(self, consumers):
        self._consumers = [str(name) for name in consumers]
        self._refresh_destination()

    def _set_default_source(self, processed_is_default, configured):
        self._processed_is_default = bool(processed_is_default)
        self._configured_source = configured or ""
        self._refresh_destination()

    def _refresh_destination(self):
        if not hasattr(self, "destination_title"):
            return
        in_use = self._running and bool(self._consumers)
        if in_use:
            self.destination_title.setText("Em uso: " + ", ".join(self._consumers))
            detail = "Sua voz tratada está chegando a esse app."
        else:
            self.destination_title.setText("Selecione Yeti Processado como microfone")
            detail = ("Nenhum app está usando o microfone tratado agora." if self._running else
                      "Ative o tratamento para ele aparecer na lista de microfones.")
        configured = self._configured_source == OUTPUT_NODE
        if configured:
            detail += " Ele é o microfone padrão do sistema."
        self.destination_detail.setText(detail)
        self.default_source_button.setText("Restaurar microfone anterior" if configured else "Usar como microfone padrão")
        self.default_source_button.setEnabled(configured or self._running)
        self.destination_card.setProperty("tone", "inUse" if in_use else "")
        self.destination_card.style().unpolish(self.destination_card)
        self.destination_card.style().polish(self.destination_card)

    def _toggle_default_source(self):
        if self._configured_source == OUTPUT_NODE:
            previous = self._preferences.previous_default_source or None
            if self._controller.set_default_source(previous):
                self._update_preferences(previous_default_source="")
        else:
            previous = self._configured_source if self._configured_source != OUTPUT_NODE else ""
            if self._controller.set_default_source(OUTPUT_NODE):
                self._update_preferences(previous_default_source=previous)

    def _update_preferences(self, **changes):
        self._preferences = replace(self._preferences, **changes)
        try:
            self._save_preferences(self._preferences)
        except OSError as error:
            self._show_error(f"Não foi possível salvar as preferências: {error}")

    def _set_status(self, status):
        self._status_text = status or "Pronto"
        self._refresh_engine_state()

    def _set_device(self, description):
        text = description.strip() if description else "Blue Yeti não detectado"
        self._device_connected = bool(description)
        self.device_label.setText(text)
        self.device_label.setToolTip(text)
        self._refresh_engine_state()

    def _set_level(self, dbfs):
        if not self._running or self._muted or not math.isfinite(dbfs):
            self._reset_meter()
            return
        level = max(-60.0, min(0.0, float(dbfs)))
        self.level_meter.setValue(round((level + 60.0) * 10))
        self.level_label.setText(f"{level:.1f} dBFS")
        self.level_status_label.setText(
            "Pico alto" if level >= -1 else "Alto" if level > -6 else
            "Boa faixa" if level >= -36 else "Baixo"
        )
        self.meter_help.setText("Fale normalmente e acompanhe o nível enviado à reunião.")
        saturated = level >= -1.0
        self.level_meter.setProperty("saturated", saturated)
        self.level_meter.style().unpolish(self.level_meter)
        self.level_meter.style().polish(self.level_meter)
        self.saturation_label.setVisible(saturated)

    def _reset_meter(self):
        self.level_meter.setValue(0)
        self.level_label.setText("— dBFS")
        self.level_status_label.setText("Silenciado" if self._muted else "Sem leitura")
        self.meter_help.setText(
            "Reative o microfone para acompanhar sua voz." if self._muted else
            "Fale normalmente para acompanhar sua voz." if self._running else
            "Aguardando a reconexão do áudio." if self._active else
            "Ative o tratamento para acompanhar sua voz."
        )
        self.level_meter.setProperty("saturated", False)
        self.saturation_label.hide()

    def _show_error(self, message):
        self.error_label.setText(message or "Não foi possível ativar o tratamento.")
        self.error_label.show()
        self.error_banner.show()

    def _dismiss_error(self):
        self.error_label.hide()
        self.error_banner.hide()

    def _record_voice_test(self):
        self._voice_action = "record"
        self._reset_calibration("Calibração não iniciada.")
        self._voice_test.record(self._settings)

    def _play_voice_test(self, mode):
        self._voice_action = "play"
        self._voice_test.play(mode)

    def _cancel_voice_test(self):
        self._voice_action = None
        was_calibrating = self._calibrating
        self._calibrating = False
        self._voice_test.cancel()
        if was_calibrating:
            self._reset_calibration("Calibração cancelada.")

    def _clear_voice_test(self):
        self._voice_action = None
        self._reset_calibration("Pronto para calibrar quando você quiser.")
        self._voice_test.clear()

    def _start_calibration(self):
        self._voice_test.cancel()
        self._reset_calibration("Prepare-se: primeiro, fique em silêncio por 3 s.")
        self._voice_action = "calibration"
        self._calibrating = True
        self._calibration_starting = True
        self.calibration_instruction.setText("Preparando a gravação…")
        try:
            self._voice_test.record(self._settings)
        finally:
            self._calibration_starting = False

    def _finish_calibration(self):
        self._voice_action = None
        sample = getattr(self._voice_test, "sample", None)
        self._calibrating = False
        try:
            result = analyze_voice_sample(sample)
        except (AttributeError, TypeError, ValueError) as error:
            self._reset_calibration(str(error))
            return
        self._calibration_result = result
        metrics = result.metrics
        self.calibration_instruction.setText("Medição concluída" if result.valid else "Vamos tentar novamente")
        self._set_calibration_stage(None)
        self.calibration_result_title.setText("Ajustes sugeridos" if result.valid else "Confira antes de repetir")
        if result.valid and result.suggestion is not None:
            self.calibration_changes_label.setText(
                f"Redução de ruído   {sample.settings.noise}% → {result.suggestion.noise}%\n"
                f"Volume da voz   {sample.settings.gain_db:+.1f} dB → {result.suggestion.gain_db:+.1f} dB"
            )
        else:
            self.calibration_changes_label.setText("Nenhum ajuste sugerido. Corrija a gravação e repita a calibração.")
        self.calibration_metrics_label.setText(
            f"Ruído {metrics.noise_dbfs:.1f} dBFS · fala {metrics.speech_dbfs:.1f} dBFS\n"
            f"Relação sinal/ruído {metrics.snr_db:.1f} dB · pico {metrics.peak_dbfs:.1f} dBFS"
        )
        self.calibration_status_label.setText(result.message)
        self.calibration_result_card.show()
        self.calibration_compare_button.show()
        self.calibration_apply_button.setEnabled(result.valid)
        QTimer.singleShot(0, self._reveal_calibration_result)

    def _reveal_calibration_result(self):
        if not self.calibration_result_card.isHidden():
            self.pages.widget(1).ensureWidgetVisible(self.calibration_apply_button, 0, 24)

    def _apply_calibration(self):
        result = self._calibration_result
        if result is None or not result.valid or result.suggestion is None:
            return
        self._update_timer.stop()
        self._load_settings(result.suggestion)
        self._commit_settings()
        self._calibration_applied = True
        self.calibration_apply_button.setEnabled(False)
        self.calibration_apply_button.setText("Ajustes aplicados")
        self.calibration_instruction.setText("Pronto para sua reunião")
        self.calibration_status_label.setText(
            "Ajustes aplicados. A clareza da gravação foi preservada."
        )

    def _reset_calibration(self, message):
        self._calibrating = False
        self._calibration_result = None
        self._calibration_applied = False
        self.calibration_apply_button.setEnabled(False)
        self.calibration_apply_button.setText("Aplicar ajustes")
        self.calibration_status_label.setText(message)
        self.calibration_instruction.setText("Tudo pronto para começar?")
        self.calibration_progress.setValue(0)
        self.calibration_result_card.hide()
        self.calibration_compare_button.hide()
        self.calibration_details_button.setChecked(False)
        self._set_calibration_stage(None)

    def _set_calibration_stage(self, stage):
        for index, card in enumerate(self.calibration_steps):
            card.setProperty("active", index == stage)
            card.style().unpolish(card)
            card.style().polish(card)

    def _voice_error(self, message):
        # A failed capture emits idle before its error; retain the action through that transition.
        if self._voice_action == "calibration":
            self._reset_calibration("A calibração falhou. Tente novamente.")
            self.calibration_instruction.setText("Não foi possível calibrar")
        self._voice_action = None
        self._show_error(message)

    def _set_voice_clip(self, has_clip):
        self._voice_has_clip = bool(has_clip)
        self.voice_snapshot_label.setVisible(self._voice_has_clip)
        if not self._voice_has_clip:
            self.voice_progress.setValue(0)
            self.calibration_compare_button.hide()
        self._update_voice_actions()

    def _set_voice_state(self, state):
        self._voice_state = state
        if state == "idle" and self._calibrating and not self._calibration_starting:
            self._reset_calibration("Calibração cancelada.")
        labels = {
            "idle": "Pronto para gravar",
            "preparing": "Preparando…",
            "recording": "Gravando…",
            "ready": "Pronto para ouvir",
            "playing_original": "Reproduzindo original…",
            "playing_processed": "Reproduzindo tratado…",
        }
        self.voice_status_label.setText(labels.get(state, "Teste de voz"))
        if state == "idle":
            self.voice_time_label.setText("—")
        elif state == "preparing":
            self.voice_time_label.setText("10 s")
            if self._calibrating:
                self.calibration_instruction.setText("Preparando a gravação…")
        elif state == "ready" and self._voice_has_clip:
            self.voice_time_label.setText("10 s gravados")
            if self._calibrating:
                self._finish_calibration()
        elif state == "ready" and self._calibrating:
            self._reset_calibration("Calibração cancelada.")
        self._update_voice_actions()

    def _set_voice_progress(self, progress):
        value = max(0.0, min(100.0, float(progress)))
        self.voice_progress.setValue(round(value))
        if self._calibrating:
            self.calibration_progress.setValue(round(value))
        if self._voice_state == "recording":
            remaining = math.ceil(10 * (100 - value) / 100)
            self.voice_time_label.setText(f"{remaining} s restantes")
            if self._calibrating:
                if value < 30:
                    text = f"Fique em silêncio — {math.ceil(3 - value / 10)} s."
                    self._set_calibration_stage(0)
                else:
                    text = f"Fale normalmente — {remaining} s restantes."
                    self._set_calibration_stage(1)
                self.calibration_instruction.setText(text)
                self.calibration_status_label.setText("A gravação fica apenas nesta sessão.")
        elif self._voice_state.startswith("playing_"):
            self.voice_time_label.setText(f"{round(value)}%")
        self.activity_status_label.setText(
            self.calibration_instruction.text() if self._calibrating else
            f"{self.voice_status_label.text()} · {self.voice_time_label.text()}"
        )

    def _update_voice_actions(self):
        active = self._voice_state in {
            "preparing",
            "recording",
            "playing_original",
            "playing_processed",
        }
        ready = self._voice_state == "ready" and self._voice_has_clip
        self.voice_record_button.setEnabled(not active)
        self.voice_original_button.setEnabled(ready)
        self.voice_processed_button.setEnabled(ready)
        self.voice_listening_help.setText(
            "Pare a reprodução atual para ouvir a outra versão."
            if self._voice_state.startswith("playing_") else
            "Escolha uma versão para ouvir. O áudio não será reproduzido automaticamente."
            if ready else "A comparação fica disponível depois da gravação."
        )
        self.voice_cancel_button.setEnabled(active)
        self.voice_cancel_button.setText(
            "Parar" if self._voice_state.startswith("playing_") else "Cancelar"
        )
        self.voice_clear_button.setEnabled(self._voice_has_clip and not active)
        self.calibration_button.setEnabled(not active)
        self.calibration_cancel_button.setEnabled(active and self._calibrating)
        self.calibration_compare_button.setEnabled(ready)
        result = self._calibration_result
        self.calibration_apply_button.setEnabled(bool(
            result and result.valid and not self._calibration_applied and not active
        ))
        self.activity_card.setVisible(active)
        playing = self._voice_state.startswith("playing_")
        self.activity_cancel_button.setText("Parar reprodução" if playing else "Cancelar gravação")
        self.activity_status_label.setText(
            self.calibration_instruction.text() if self._calibrating else self.voice_status_label.text()
        )

    def set_shortcut_status(self, text):
        self.shortcut_label.setText(text or "Atalho global indisponível")

    def set_tray_available(self, available):
        self.tray_help.setText("Fechar → bandeja" if available else "Fechar encerra o app")
        self.tray_help.setToolTip(
            "Fechar a janela mantém o app aberto. Use Encerrar Vozena no menu da bandeja para sair."
            if available else "Sem bandeja disponível. Fechar a janela encerra o app e o tratamento da voz."
        )

    def closeEvent(self, event: QCloseEvent):
        if self._update_timer.isActive():
            self._save_settings(self._settings)
        self._update_timer.stop()
        if self._voice_test is not None:
            self._voice_test.close()
        self._controller.stop()
        event.accept()

    def _apply_theme(self):
        self.setStyleSheet(
            """
            QWidget { color: #eff5fa; font-size: 14px; }
            QWidget#root, QWidget#pageSurface, QScrollArea#tabScroll,
            QTabWidget#pages { background: #111820; }
            QScrollBar:vertical { background: #111820; width: 8px; margin: 4px 0; }
            QScrollBar::handle:vertical { background: #415260; border-radius: 4px;
                                          min-height: 36px; }
            QScrollBar::handle:vertical:hover { background: #637a89; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0; background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QLabel#wordmark { background: transparent; color: #3be0c5;
                              font-size: 27px; font-weight: 700; border-radius: 13px; }
            QLabel#title { font-size: 27px; font-weight: 700; }
            QLabel#subtitle, QLabel#help, QLabel#intro { color: #aabac6; }
            QLabel#subtitle { font-size: 13px; }
            QLabel#eyebrow { color: #80c8bd; font-size: 11px; font-weight: 600; }
            QLabel#pageTitle { font-size: 22px; font-weight: 600; }
            QLabel#intro { font-size: 14px; }
            QLabel#help, QLabel#controlHelp { font-size: 12px; color: #aabac6; }
            QLabel#sectionLabel, QLabel#controlLabel { font-weight: 600; }
            QLabel#instruction { font-size: 21px; font-weight: 600; }
            QLabel#sliderValue { color: #82e5d5; font-weight: 600; }
            QLabel#technical, QLabel#privacy, QLabel#footer { color: #99abb8; font-size: 12px; }
            QLabel#snapshot { color: #82e5d5; font-size: 12px; }
            QLabel#warning { color: #ffd299; font-size: 12px; }
            QLabel#resultValue { color: #d5f4ec; font-size: 16px; }
            QFrame#card, QFrame#stepCard { background: #19232d;
                border: 1px solid #2b3845; border-radius: 12px; }
            QFrame#sessionHeader { background: #19232d;
                border: 1px solid #354653; border-radius: 14px; }
            QFrame#sessionHeader[tone="active"] { border-color: #39756b; }
            QFrame#sessionHeader[tone="muted"] { border-color: #a3606a; }
            QFrame#sessionHeader[tone="waiting"] { border-color: #8b744e; }
            QLabel#deviceLabel { font-weight: 600; }
            QLabel#sessionStatus { color: #aabac6; font-size: 13px; }
            QLabel#stateDot { color: #99abb8; font-size: 18px; }
            QLabel#stateLabel { color: #c4d0d9; background: #2b3845;
                padding: 4px 10px; border-radius: 10px; font-size: 12px; font-weight: 600; }
            QLabel#stateDot[tone="active"] { color: #3be0c5; }
            QLabel#stateLabel[tone="active"] { color: #90ecd9; background: #20463f; }
            QLabel#stateDot[tone="muted"] { color: #ffa8b2; }
            QLabel#stateLabel[tone="muted"] { color: #ffd6da; background: #55313a; }
            QLabel#stateDot[tone="waiting"] { color: #ffd299; }
            QLabel#stateLabel[tone="waiting"] { color: #ffe0b5; background: #493e2b; }
            QFrame#destinationCard { background: #172d2b;
                border: 1px solid #294b45; border-radius: 10px; }
            QLabel#destination { color: #d0f4ea; font-weight: 600; }
            QLabel#destinationDetail { color: #a9cfc6; font-size: 12px; }
            QFrame#destinationCard[tone="inUse"] { background: #163a31; border-color: #3b8b77; }
            QFrame#stepCard[active="true"], QFrame#resultCard { background: #17322d;
                border: 1px solid #3b8b77; border-radius: 12px; }
            QFrame#activityCard { background: #22343d;
                border: 1px solid #496b7a; border-radius: 10px; }
            QFrame#errorBanner { background: #3b252e;
                border: 1px solid #985666; border-radius: 10px; }
            QLabel#error { color: #ffd6da; font-size: 13px; }
            QLabel#levelStatus { color: #c4d0d9; font-size: 12px; padding-left: 6px; }
            QTabWidget#pages::pane { border: 0; border-top: 1px solid #2b3845; }
            QTabBar::tab { color: #aabac6; background: #111820;
                padding: 12px 18px; border: 0; border-bottom: 3px solid transparent; }
            QTabBar::tab:hover { color: #eff5fa; background: #19232d; }
            QTabBar::tab:selected { color: #82e5d5; border-bottom-color: #3be0c5;
                font-weight: 600; }
            QTabBar::tab:focus { background: #253d44; }
            QComboBox, QPushButton { background: #26333f; color: #eff5fa;
                border: 2px solid #3b4b5a; border-radius: 8px; padding: 8px 12px; }
            QComboBox:hover, QPushButton:hover { background: #2e4050; border-color: #637a89; }
            QComboBox:focus, QPushButton:focus { border-color: #b4f8eb; }
            QPushButton:pressed { background: #172d2b; }
            QPushButton:disabled { color: #82939f; background: #1c2630; border-color: #2b3845; }
            QPushButton#primaryButton { background: #3be0c5; border-color: #3be0c5;
                color: #09231d; font-weight: 600; }
            QPushButton#primaryButton:hover { background: #75ead6; border-color: #75ead6; }
            QPushButton#primaryButton:pressed { background: #24b99f; }
            QPushButton#primaryButton[sessionActive="true"] { background: #26333f;
                color: #eff5fa; border-color: #637a89; }
            QPushButton#primaryButton:focus { border-color: #f1fffb; }
            QPushButton#primaryButton:disabled { background: #1c2630;
                border-color: #2b3845; color: #82939f; }
            QPushButton#muteButton:checked { background: #713747;
                border-color: #dc8998; color: #ffe9ed; }
            QPushButton#muteButton:checked:hover { background: #894357; }
            QPushButton#muteButton:checked:focus { border-color: #ffccd5; }
            QPushButton#muteButton:disabled { background: #1c2630;
                border-color: #2b3845; color: #82939f; }
            QPushButton#modeButton:checked { background: #20463f;
                border-color: #3be0c5; color: #bcf7e9; }
            QPushButton#modeButton:checked:focus { border-color: #f1fffb; }
            QPushButton#modeButton:disabled { background: #1c2630;
                border-color: #2b3845; color: #82939f; }
            QPushButton#modeButton:checked:disabled { background: #1c302d;
                border-color: #537f77; color: #aecbc4; }
            QPushButton#quietButton { background: transparent; border-color: transparent;
                color: #c2d0da; }
            QPushButton#quietButton:hover, QPushButton#quietButton:checked { background: #26333f; }
            QPushButton#quietButton:focus { border-color: #b4f8eb; }
            QPushButton#quietButton:disabled { color: #82939f; }
            QComboBox { min-width: 165px; padding-right: 28px; }
            QComboBox::drop-down { border: 0; width: 26px; }
            QComboBox::down-arrow { image: url("CHEVRON_PATH"); width: 12px; height: 12px; }
            QComboBox QAbstractItemView { background: #26333f; color: #eff5fa;
                selection-background-color: #20463f; selection-color: #bcf7e9;
                border: 1px solid #637a89; padding: 4px; }
            QSlider { min-height: 26px; }
            QSlider:focus { background: #233942; border-radius: 5px; }
            QSlider::groove:horizontal { height: 5px; background: #415260;
                border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #3be0c5; border-radius: 2px; }
            QSlider::handle:horizontal { background: #d5f4ec; border: 2px solid #3be0c5;
                width: 16px; margin: -7px 0; border-radius: 10px; }
            QSlider::handle:horizontal:hover { background: #ffffff; }
            QSlider::handle:horizontal:focus { border: 2px solid #ffffff; background: #3be0c5; }
            QProgressBar#levelMeter, QProgressBar#voiceProgress { background: #0d141b;
                border: 0; border-radius: 4px; min-height: 8px; max-height: 8px; }
            QProgressBar#levelMeter::chunk, QProgressBar#voiceProgress::chunk {
                background: #3be0c5; border-radius: 4px; }
            QProgressBar#levelMeter[saturated="true"]::chunk { background: #ffd299; }
            """.replace("CHEVRON_PATH", str(Path(__file__).resolve().parent.parent / "assets/chevron-down.svg"))
        )
