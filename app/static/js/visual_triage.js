/**
 * OncoTriage Visual Triage — Alpine.js component
 * Mobile camera capture → Gemini Vision → COSTaRS triage
 */

const TRIAGE_COLORS = {
  EMERGENCY: 'border-red-500 bg-red-50 text-red-800',
  URGENT: 'border-orange-500 bg-orange-50 text-orange-800',
  ROUTINE: 'border-yellow-500 bg-yellow-50 text-yellow-700',
  SELF_CARE: 'border-green-500 bg-green-50 text-green-800',
};

const AE_ICONS = {
  papulopustular_eruption: '🌡️',
  hand_foot_syndrome: '🤲',
  checkpoint_dermatitis: '🔬',
  radiation_dermatitis: '☢️',
  oral_mucositis: '👄',
  unsure: '🔍',
};

const GRADE_BADGE_COLORS = {
  1: 'bg-green-100 text-green-800',
  2: 'bg-yellow-100 text-yellow-800',
  3: 'bg-orange-100 text-orange-800',
  4: 'bg-red-100 text-red-800',
};

function visualTriage(aeTypesData, triageActionsData, processingStepsData) {
  return {
    step: 1,
    aeTypes: aeTypesData || [],
    selectedAE: null,
    modalities: [],
    cancerType: '',
    selectedLocations: [],
    thrombocytopeniaHistory: false,
    selectedFile: null,
    previewUrl: null,
    fileSizeWarning: false,
    errorMsg: '',
    analysisError: null,   // { message, retry_after, providers_tried } — transient provider failure
    retryCountdown: 0,
    _retryCountdownTimer: null,
    result: null,
    processingStep: 0,
    processingSteps: processingStepsData || (() => { console.warn('[OncoTriage] processingStepsData missing — check locale template'); return ['[missing: visual_triage.processing.uploading]']; })(),
    processingMessage: (processingStepsData || ['[missing: visual_triage.processing.uploading]'])[0],
    triageActions: triageActionsData || {},
    _processingTimer: null,

    // ── AE selection ────────────────────────────────────────────────────────
    selectAE(ae) {
      this.selectedAE = ae;
    },

    aeIcon(id) {
      return AE_ICONS[id] || '📷';
    },

    getLabel(labelObj) {
      if (!labelObj) return '';
      if (typeof labelObj === 'string') return labelObj;
      const lang = document.documentElement.lang || 'en';
      return labelObj[lang] || labelObj['en'] || '';
    },

    toggleModality(code) {
      const idx = this.modalities.indexOf(code);
      if (idx === -1) {
        this.modalities.push(code);
      } else {
        this.modalities.splice(idx, 1);
      }
    },

    goToCapture() {
      if (!this.selectedAE) return;
      this.step = 2;
      this.errorMsg = '';
    },

    // ── Camera / file handling ──────────────────────────────────────────────
    handleFileSelect(event) {
      const file = event.target.files[0];
      if (!file) return;

      const MAX_BYTES = 10 * 1024 * 1024;
      this.fileSizeWarning = file.size > MAX_BYTES;
      this.selectedFile = file;
      this.errorMsg = '';

      const reader = new FileReader();
      reader.onload = (e) => {
        this.previewUrl = e.target.result;
      };
      reader.readAsDataURL(file);
    },

    clearImage() {
      this.selectedFile = null;
      this.previewUrl = null;
      this.fileSizeWarning = false;
      this.$refs.fileInput.value = '';
    },

    toggleLocation(loc) {
      const idx = this.selectedLocations.indexOf(loc);
      if (idx === -1) {
        this.selectedLocations.push(loc);
      } else {
        this.selectedLocations.splice(idx, 1);
      }
    },

    // ── Submission ──────────────────────────────────────────────────────────
    async submitImage() {
      if (!this.selectedFile || this.fileSizeWarning) return;

      this.errorMsg = '';
      this.analysisError = null;
      this.step = 3;
      this.processingStep = 0;
      this._startProcessingTimer();

      const formData = new FormData();
      formData.append('image', this.selectedFile);
      formData.append('suspected_ae', this.selectedAE.id);
      formData.append('treatment_modalities', JSON.stringify(this.modalities));
      formData.append('cancer_type', this.cancerType);
      formData.append('locale', document.documentElement.lang || 'en');
      formData.append('anatomical_location', this.selectedLocations.join(', '));
      formData.append('thrombocytopenia_history', this.thrombocytopeniaHistory ? 'true' : 'false');

      try {
        const resp = await fetch('/visual-triage/analyze', {
          method: 'POST',
          body: formData,
        });

        clearInterval(this._processingTimer);
        this.processingStep = this.processingSteps.length;

        let data;
        try {
          data = await resp.json();
        } catch {
          data = { detail: resp.statusText || 'Server error' };
        }

        if (!resp.ok) {
          const detail = data.detail;

          // 503 structured: all vision providers failed → stay on step 3, show orange error card
          if (
            resp.status === 503 &&
            detail &&
            typeof detail === 'object' &&
            detail.error === 'all_providers_failed'
          ) {
            this.analysisError = detail;
            if (detail.retry_after) this._startRetryCountdown(detail.retry_after);
            return;
          }

          // Other 5xx / 422: server error → stay on step 3 with generic error card
          if (resp.status >= 500 || resp.status === 422) {
            this.analysisError = {
              error: 'server_error',
              message:
                typeof detail === 'string'
                  ? detail
                  : detail?.message || 'Vision analysis failed. Please try again.',
              retry_after: null,
              providers_tried: [],
            };
            return;
          }

          // 400 / 413: user input error → go back to step 2
          this.step = 2;
          this.errorMsg =
            typeof detail === 'string'
              ? detail
              : detail?.message || 'Please check your image and try again.';
          return;
        }

        this.result = data;
        await new Promise((r) => setTimeout(r, 600));
        this.step = 4;
        this._announceResult(data);
      } catch (err) {
        // Network-level failure (fetch threw) — stay on step 3 with error card
        clearInterval(this._processingTimer);
        this.analysisError = {
          error: 'network_error',
          message: 'Network error. Please check your connection and try again.',
          retry_after: null,
          providers_tried: [],
        };
      }
    },

    retryAnalysis() {
      clearInterval(this._retryCountdownTimer);
      this.retryCountdown = 0;
      this.analysisError = null;
      this.submitImage();
    },

    skipToSymptomTriage() {
      // Navigate to the text-based symptom triage flow
      window.location.href = '/triage';
    },

    _startProcessingTimer() {
      let idx = 0;
      this._processingTimer = setInterval(() => {
        idx = Math.min(idx + 1, this.processingSteps.length - 1);
        this.processingStep = idx;
        this.processingMessage = this.processingSteps[idx];
      }, 3000);
    },

    _startRetryCountdown(seconds) {
      this.retryCountdown = seconds;
      clearInterval(this._retryCountdownTimer);
      this._retryCountdownTimer = setInterval(() => {
        this.retryCountdown = Math.max(0, this.retryCountdown - 1);
        if (this.retryCountdown === 0) {
          clearInterval(this._retryCountdownTimer);
        }
      }, 1000);
    },

    retake() {
      this.step = 2;
      this.result = null;
      this.analysisError = null;
      clearInterval(this._retryCountdownTimer);
      this.retryCountdown = 0;
      this.clearImage();
    },

    // ── Styling helpers ─────────────────────────────────────────────────────
    triageLevelStyle(level) {
      return TRIAGE_COLORS[level] || 'border-stone-300 bg-stone-50 text-stone-700';
    },

    triageLevelAction(level) {
      const key = level?.toLowerCase();
      if (key && this.triageActions[key]) return this.triageActions[key];
      if (!this.triageActions || Object.keys(this.triageActions).length === 0) {
        console.warn('[OncoTriage] triageActionsData missing — check locale template');
        return `[missing: triage.action.${(level || 'unknown').toLowerCase()}]`;
      }
      return '';
    },

    ctcaeGradeBadgeColor(grade) {
      return GRADE_BADGE_COLORS[grade] || 'bg-stone-100 text-stone-700';
    },

    gradeToSeverity(grade) {
      return { 1: 'Mild', 2: 'Moderate', 3: 'Severe', 4: 'Critical' }[grade] || '—';
    },

    // ── Accessibility ───────────────────────────────────────────────────────
    _announceResult(data) {
      const level = data?.triage_level || 'unknown';
      const grade = data?.assessment?.ctcae_grade_visual?.grade;
      const msg = grade
        ? `Triage result: ${level}. Visual CTCAE Grade ${grade}.`
        : `Triage result: ${level}.`;

      const liveRegion = document.createElement('div');
      liveRegion.setAttribute('role', 'status');
      liveRegion.setAttribute('aria-live', 'polite');
      liveRegion.setAttribute('aria-atomic', 'true');
      liveRegion.className = 'sr-only';
      liveRegion.textContent = msg;
      document.body.appendChild(liveRegion);
      setTimeout(() => liveRegion.remove(), 3000);
    },
  };
}
