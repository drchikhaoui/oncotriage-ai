# Clinical Foundation — OncoTriage AI

## Overview

OncoTriage is built on validated, peer-reviewed clinical instruments and national guidelines. Every triage rule is traceable to a specific guideline version and publication. This document serves as the evidence registry for all clinical decisions embedded in the system.

---

## 1. Symptom Grading Framework: NCI CTCAE v5.0

**Full Name:** NCI Common Terminology Criteria for Adverse Events, Version 5.0  
**Publisher:** U.S. Department of Health and Human Services, National Institutes of Health, National Cancer Institute  
**Date:** November 27, 2017  
**URL:** https://ctep.cancer.gov/protocoldevelopment/electronic_applications/ctc.htm  
**Role in OncoTriage:** Authoritative grading framework for all 10 symptom domains.

### CTCAE Grade Definitions
| Grade | Meaning |
|-------|---------|
| 1 | Mild — asymptomatic or mild symptoms; clinical or diagnostic observations only |
| 2 | Moderate — minimal, local, or noninvasive intervention indicated; limiting instrumental ADL |
| 3 | Severe — severe or medically significant but not immediately life-threatening; hospitalization may be indicated; limiting self-care ADL |
| 4 | Life-threatening consequences; urgent intervention indicated |
| 5 | Death related to adverse event |

ADL = Activities of Daily Living; Instrumental ADL includes cooking, shopping, finances; Self-care ADL includes bathing, dressing, feeding.

---

## 2. Triage Logic: NCCN Clinical Practice Guidelines

All triage thresholds and escalation rules are derived from NCCN guidelines. NCCN (National Comprehensive Cancer Network) guidelines are the most widely used and evidence-based oncology clinical practice guidelines in the United States.

### 2.1 Febrile Neutropenia
**Guideline:** NCCN Clinical Practice Guidelines in Oncology — Prevention and Treatment of Cancer-Related Infections, v2.2024  
**Rule:** Temperature ≥38.3°C (single) OR ≥38.0°C sustained for ≥1 hour in a patient who has received cytotoxic chemotherapy within the previous 14 days → **EMERGENCY triage**  
**Rationale:** Febrile neutropenia carries up to 10-15% 30-day mortality without immediate broad-spectrum antibiotic treatment. Time to antibiotics is a quality metric (target: within 60 minutes of presentation).  
**Supporting Evidence:**
- Freifeld AG, et al. "Clinical Practice Guideline for the Use of Antimicrobial Agents in Neutropenic Patients with Cancer: 2010 Update by the IDSA." *Clinical Infectious Diseases* 2011;52:e56–e93.
- Klastersky J, et al. "Management of febrile neutropaenia: ESMO Clinical Practice Guidelines." *Annals of Oncology* 2016;27(suppl 5):v111–v118.

### 2.2 Nausea and Vomiting
**Guideline:** NCCN Antiemesis v2.2024  
**Rules:**  
- Grade 3 vomiting (≥6 episodes/24h) → **URGENT** (IV hydration, antiemetic escalation)  
- Grade 2 vomiting → **ROUTINE** (antiemetic optimization)  
**Supporting Evidence:**
- Roila F, et al. "Guideline update for MASCC and ESMO in the prevention of chemotherapy and radiotherapy-induced nausea and vomiting." *Annals of Oncology* 2016;27(suppl 5):v119–v133.
- Hesketh PJ, et al. ASCO guideline, *J Clin Oncol* 2020;38:2782–2797.

### 2.3 Diarrhea
**Guideline:** NCCN Survivorship v2.2024  
**Rules:**  
- Grade 3+ diarrhea (≥7 stools/day above baseline) → **URGENT** (IV hydration, electrolytes, C. diff screen)  
**Supporting Evidence:**
- Benson AB, et al. "Recommended guidelines for the treatment of cancer treatment-induced diarrhea." *J Clin Oncol* 2004;22:2918–2926.
- Andreyev J, et al. "Guidance on the management of diarrhoea during cancer chemotherapy." *Lancet Oncol* 2014;15:e447–460.

### 2.4 Cancer Pain
**Guideline:** NCCN Adult Cancer Pain v2.2024  
**Rules:**  
- Grade 4 pain (NRS 10/10) → **EMERGENCY** (rule out cord compression, obstruction)  
- Grade 3 uncontrolled pain (NRS 7-9, unresponsive to current regimen) → **URGENT** (opioid titration)  
- Grade 3 pain (controlled) → **URGENT**  
**Supporting Evidence:**
- NCCN Clinical Practice Guidelines in Oncology: Adult Cancer Pain. v2.2024.
- WHO. "Cancer Pain Relief." 2nd edition. Geneva: WHO; 1996. (Three-step analgesic ladder)
- Caraceni A, et al. "Use of opioid analgesics in the treatment of cancer pain." *Lancet Oncol* 2012;13:e58–68.

### 2.5 Dyspnea
**Guideline:** NCCN Survivorship v2.2024; CTCAE v5.0  
**Rules:**  
- Grade 3+ dyspnea (shortness of breath at rest) → **EMERGENCY**  
- Grade 2 dyspnea (with minimal exertion) → **URGENT**  
**Rationale:** In oncology patients, dyspnea at rest requires emergency evaluation to rule out pulmonary embolism (4-7x higher risk in cancer), malignant pleural effusion, pericardial tamponade, or pneumonitis (in checkpoint inhibitor therapy).  
**Supporting Evidence:**
- Khorana AA, et al. "Thromboembolism is a leading cause of death in cancer patients receiving outpatient chemotherapy." *J Thromb Haemost* 2007;5:632–634.
- Lyman GH, et al. ASCO guideline on VTE prophylaxis. *J Clin Oncol* 2021;39:3826–3846.

### 2.6 Bleeding
**Guideline:** NCCN Hematopoietic Growth Factors v2.2024  
**Rules:**  
- Any bleeding in patient with thrombocytopenia history → **URGENT minimum**  
- Grade 3+ bleeding → **EMERGENCY**  
**Supporting Evidence:**
- Schiffer CA, et al. "Platelet Transfusion for Patients with Cancer: ASCO Clinical Practice Guideline Update." *J Clin Oncol* 2018;36:283–299.

### 2.7 Mucositis
**Guideline:** NCCN Prevention and Treatment of Cancer-Related Infections; Multinational Association of Supportive Care in Cancer (MASCC) guidelines  
**Rules:**  
- Grade 3+ mucositis (severe pain, unable to eat) → **URGENT**  
**Supporting Evidence:**
- Lalla RV, et al. "MASCC/ISOO clinical practice guidelines for the management of mucositis secondary to cancer therapy." *Cancer* 2014;120:1453–1461.

### 2.8 Peripheral Neuropathy
**Guideline:** NCCN Survivorship v2.2024 — CIPN section  
**Rules:**  
- Grade 2-3 CIPN → **ROUTINE** (dose modification consideration, duloxetine)  
**Supporting Evidence:**
- Loprinzi CL, et al. "Prevention and Management of Chemotherapy-Induced Peripheral Neuropathy in Survivors of Adult Cancers: ASCO Guideline Update." *J Clin Oncol* 2020;38:3325–3348.
- Smith EML, et al. (duloxetine CIPN trial) *JAMA* 2013;309:1359–1367. 

### 2.9 Fatigue
**Guideline:** NCCN Cancer-Related Fatigue v2.2024  
**Rules:**  
- Grade 3 fatigue (limiting self-care ADL) → **ROUTINE** (CBC, TSH, PHQ-9 workup)  
**Supporting Evidence:**
- Bower JE, et al. "Screening, Assessment, and Management of Fatigue in Adult Survivors of Cancer: An American Society of Clinical Oncology Clinical Practice Guideline Adaptation." *J Clin Oncol* 2014;32:1840–1850.

---

## 3. Red Flag Combinations

### 3.1 Malignant Spinal Cord Compression
**Rule:** Back pain + bilateral leg weakness/saddle anesthesia in cancer patient → **EMERGENCY**  
**Citation:** Loblaw DA, et al. "A systematic review of diagnosis and management of malignant extradural spinal cord compression: the Cancer Care Ontario Practice Guidelines Initiative's Neuro-Oncology Disease Site Group." *J Clin Oncol* 2005;23:2028–2037.

### 3.2 Superior Vena Cava Syndrome
**Rule:** Dyspnea + facial/arm swelling + neck vein distension → **EMERGENCY**  
**Citation:** Wilson LD, et al. "Superior vena cava syndrome with malignant causes." *NEJM* 2007;356:1862–1869.

### 3.3 Neutropenic Enterocolitis (Typhlitis)
**Rule:** Febrile neutropenia + right lower quadrant pain + abdominal distension → **EMERGENCY**  
**Citation:** Gorschlüter M, et al. "Neutropenic enterocolitis in adults." *Leukemia & Lymphoma* 2005;46:651–662.

---

## 4. Safety Architecture: HIPAA Considerations

- **No PHI stored**: Session IDs are anonymous UUIDs. No name, DOB, MRN, or address fields exist in the schema.
- **LLM prompts**: Raw free text is processed by the LLM but only structured extracted fields are persisted. The raw text field (`raw_text`) is explicitly not stored in the database.
- **Audit trail**: Every triage decision is logged with the rule IDs that fired, enabling full auditability without storing patient content.
- **Deterministic fallback**: The system operates fully without LLM if `DISABLE_LLM=true`, ensuring clinical decisions remain deterministic and auditable.

---

## 5. Limitations and Future Validation

This prototype requires prospective clinical validation before deployment in any clinical setting:

1. **Sensitivity/specificity analysis** against gold standard (physician triage decisions) using retrospective oncology EMR data.
2. **IRB approval** for prospective validation study.
3. **FDA SaMD consideration**: Under FDA's Software as a Medical Device guidance, this tool likely falls under Class II (moderate risk) requiring a 510(k) submission, contingent on intended use.
4. **Planned improvements**:
   - Wearable data integration (Empatica E4/E4 Connect for continuous HR, EDA, temperature)
   - HealthKit integration for passive monitoring
   - Multilingual support (Arabic, French — per patient population needs)
   - Probabilistic risk scoring rather than binary rule triggers

---

*Last updated: 2024 | Evidence base reviewed against NCCN v2.2024, CTCAE v5.0, ASCO guidelines*
