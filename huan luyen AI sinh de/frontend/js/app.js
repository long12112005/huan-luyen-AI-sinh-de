/* =========================================================================
   LOGIC FRONTEND CHO HỆ THỐNG WEB AI EXAMGEN (GIAO DIỆN STUDIO HIỆN ĐẠI)
   - Bố cục 2 bước tách biệt tại Tab 1:
     + Bước 1: Thiết lập Tài liệu & Ma trận Đề thi (2 cột cân đối 1:1)
     + Bước 2: Bản Xem Trước, Chỉnh Sửa & Xuất Bản Bộ Đề (Full-width Studio)
   - Tab 5 tách 2 Sub-tabs:
     + Sub-tab 1: Đồ thị hội tụ Loss SVG & Thanh tiến trình phân bố dữ liệu
     + Sub-tab 2: Master-Detail 3.600 mẫu Dataset & ChatML Inspector đối chiếu
========================================================================= */

let authToken = localStorage.getItem("aiexam_token") || "";
let currentUser = null;
let currentActiveExam = null;
let currentDocumentId = null;
let allUserExams = [];
let userDocumentsCache = [];

// Biến phục vụ phòng thi thử
let quizExamData = null;
let quizAnswers = {};
let quizTimer = null;
let quizRemainingSec = 900;
let quizElapsedSec = 0;

// Biến phục vụ Trình duyệt 3.600 mẫu Dataset (Tab 5)
let explorerCurrentPage = 1;
let explorerTotalPages = 1;
let explorerCurrentItems = [];
let explorerSelectedId = "";
let explorerSearchTimer = null;

function showToast(msg) {
  const el = document.getElementById("toastNotification");
  if (!el) return;
  el.innerText = msg;
  el.style.display = "block";
  setTimeout(() => {
    el.style.display = "none";
  }, 3200);
}

// Chuyển đổi giao diện Sáng / Tối (Dark Cosmic Mode) chuẩn Gaming Edu
function applyThemeState(isDark) {
  document.documentElement.classList.toggle("dark", isDark);
  const moonIcon = document.getElementById("themeIconMoon");
  const sunIcon = document.getElementById("themeIconSun");
  if (moonIcon) moonIcon.style.display = isDark ? "none" : "block";
  if (sunIcon) sunIcon.style.display = isDark ? "block" : "none";
}

function toggleDarkMode() {
  const nextDark = !document.documentElement.classList.contains("dark");
  localStorage.setItem("aiexam_theme", nextDark ? "dark" : "light");
  applyThemeState(nextDark);
  showToast(nextDark ? "🌙 Đã chuyển sang chế độ Dark Cosmic (Gaming Edu)" : "☀️ Đã chuyển sang chế độ Sáng (Workspace)");
}

const GAME_OPT_SHAPES = { A: "▲", B: "◆", C: "●", D: "■" };

function getBloomBadge(diff) {
  if (diff === "Nhận biết") return "badge-nb";
  if (diff === "Thông hiểu") return "badge-th";
  if (diff === "Vận dụng") return "badge-vd";
  return "badge-vdc";
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function apiFetch(url, options = {}) {
  const headers = options.headers || {};
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }
  if (options.body && typeof options.body === "object" && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  options.headers = headers;
  const res = await fetch(url, options);
  if (res.status === 401) {
    clearSessionAndShowAuth();
    throw new Error("Phiên đăng nhập đã hết hạn.");
  }
  return res;
}

/* =========================================================================
   1. ĐĂNG NHẬP, ĐĂNG KÝ & QUẢN LÝ PHIÊN TÀI KHOẢN
========================================================================= */
function switchAuthTab(mode) {
  const isLogin = mode === "login";
  document.getElementById("tabBtnLogin").classList.toggle("active", isLogin);
  document.getElementById("tabBtnRegister").classList.toggle("active", !isLogin);
  document.getElementById("loginFormPane").style.display = isLogin ? "block" : "none";
  document.getElementById("registerFormPane").style.display = isLogin ? "none" : "block";
}

async function handleLogin() {
  const email = document.getElementById("loginEmail").value.trim();
  const password = document.getElementById("loginPassword").value;
  if (!email || !password) {
    alert("Vui lòng nhập đầy đủ Email và Mật khẩu.");
    return;
  }

  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) {
    alert(data.detail || "Đăng nhập thất bại.");
    return;
  }
  onAuthSuccess(data.token, data.user);
}

function quickDemoLogin() {
  document.getElementById("loginEmail").value = "demo@aiexam.vn";
  document.getElementById("loginPassword").value = "123456";
  handleLogin();
}

async function handleRegister() {
  const full_name = document.getElementById("regFullName").value.trim();
  const email = document.getElementById("regEmail").value.trim();
  const password = document.getElementById("regPassword").value;
  const role = document.getElementById("regRole").value;

  if (!full_name || !email || password.length < 4) {
    alert("Vui lòng điền đầy đủ Họ tên, Email và Mật khẩu (ít nhất 4 ký tự).");
    return;
  }

  const res = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ full_name, email, password, role }),
  });
  const data = await res.json();
  if (!res.ok) {
    alert(data.detail || "Đăng ký không thành công.");
    return;
  }
  showToast("Đã tạo tài khoản thành công!");
  onAuthSuccess(data.token, data.user);
}

function onAuthSuccess(token, user) {
  authToken = token;
  currentUser = user;
  localStorage.setItem("aiexam_token", token);

  document.getElementById("authScreen").style.display = "none";
  document.getElementById("appScreen").style.display = "flex";

  document.getElementById("userNameDisplay").innerText = user.full_name;
  document.getElementById("userRoleDisplay").innerText = `${user.role} (${user.email})`;
  document.getElementById("userAvatarLetter").innerText = (user.full_name || "U")[0].toUpperCase();

  initializeUserWorkspace();
}

async function handleLogout() {
  if (authToken) {
    await fetch("/api/auth/logout", {
      method: "POST",
      headers: { Authorization: `Bearer ${authToken}` },
    });
  }
  clearSessionAndShowAuth();
}

function clearSessionAndShowAuth() {
  authToken = "";
  currentUser = null;
  localStorage.removeItem("aiexam_token");
  document.getElementById("appScreen").style.display = "none";
  document.getElementById("authScreen").style.display = "flex";
}

/* =========================================================================
   2. ĐIỀU HƯỚNG CÁC PHÂN HỆ & CHUYỂN ĐỔI BƯỚC CÔNG VIỆC
========================================================================= */
function openTab(tabName, btnElem) {
  document.querySelectorAll(".tab-pane").forEach((el) => el.classList.remove("active"));
  document.getElementById("tab-" + tabName).classList.add("active");

  if (btnElem) {
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
    btnElem.classList.add("active");
  }

  const headerMap = {
    generate: {
      title: "Thiết Kế & Sinh Đề Thi Bằng AI",
      sub: "Trích xuất ngữ cảnh từ tài liệu, cấu hình ma trận Bloom và xuất bản đề thi",
    },
    myexams: {
      title: "Kho Lưu Trữ Bộ Đề Của Tôi",
      sub: "Quản lý toàn bộ các bộ đề đã tạo, chỉnh sửa câu hỏi hoặc tải về máy",
    },
    quiz: {
      title: "Phòng Thi Thử & Chấm Điểm Tự Động",
      sub: "Hỗ trợ làm bài và chấm điểm tự động cả 4 dạng: Trắc nghiệm, Điền khuyết, Ghép cặp & Tự luận",
    },
    history: {
      title: "Lịch Sử Hoạt Động & Kho Tài Liệu Đã Đọc",
      sub: "Theo dõi thống kê tài khoản, điểm số các lần thi thử và tái sử dụng tài liệu nguồn",
    },
    training: {
      title: "Huấn Luyện AI (QLoRA 4-bit) & Kho Dữ Liệu 3.600 Mẫu",
      sub: "Giám sát hội tụ hàm mất mát (Loss Curve) và kiểm định trực tiếp 3.600 mẫu ChatML đa nguồn",
    },
  };
  const info = headerMap[tabName] || { title: "", sub: "" };
  document.getElementById("topbarTitle").innerText = info.title;
  const subEl = document.getElementById("topbarSubtitle");
  if (subEl) subEl.innerText = info.sub;

  if (tabName === "myexams") loadMySavedExams();
  if (tabName === "quiz") setupQuizSelector();
  if (tabName === "history") loadHistoryAndDocuments();
  if (tabName === "training") {
    loadTrainingPipelineInfo();
    loadDatasetExplorer(1);
  }
}

function switchStudioStep(stepMode) {
  const isConfig = stepMode === "config";
  const btnCfg = document.getElementById("stepBtnConfig");
  const btnPrv = document.getElementById("stepBtnPreview");
  const viewCfg = document.getElementById("studioViewConfig");
  const viewPrv = document.getElementById("studioViewPreview");

  if (btnCfg) btnCfg.classList.toggle("active", isConfig);
  if (btnPrv) btnPrv.classList.toggle("active", !isConfig);
  if (viewCfg) viewCfg.style.display = isConfig ? "grid" : "none";
  if (viewPrv) viewPrv.style.display = isConfig ? "none" : "grid";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function switchTrainingSubtab(mode) {
  const isOverview = mode === "overview";
  document.getElementById("subtabBtnOverview").classList.toggle("active", isOverview);
  document.getElementById("subtabBtnExplorer").classList.toggle("active", !isOverview);
  document.getElementById("trainingViewOverview").style.display = isOverview ? "grid" : "none";
  document.getElementById("trainingViewExplorer").style.display = isOverview ? "none" : "block";
}

async function initializeUserWorkspace() {
  await loadSavedDocumentsDropdown();
  const res = await apiFetch("/api/exams");
  allUserExams = await res.json();
  if (allUserExams.length > 0) {
    const firstDetail = await (await apiFetch(`/api/exams/${allUserExams[0].id}`)).json();
    renderActiveExam(firstDetail);
  } else {
    document.getElementById("generatedQuestionsList").innerHTML = `
      <div style="text-align:center; padding:45px 20px; color:var(--text-muted);">
        Tài khoản của bạn chưa có bộ đề nào. Hãy quay lại Bước 1 để tải tài liệu và nhấn <strong>"Sinh Bộ Đề Ngay"</strong>!
      </div>
    `;
  }
}

/* =========================================================================
   3. ĐỌC TÀI LIỆU (.PDF, .DOCX, .TXT, .MD) & MA TRẬN ĐỀ THI BLOOM
========================================================================= */
function syncQuestionCount(val) {
  const n = Math.max(1, Math.min(50, parseInt(val || "5")));
  document.getElementById("rangeQuestionCount").value = Math.min(30, n);
  document.getElementById("numQuestionCount").value = n;

  const diffFilter = document.getElementById("genDifficultyFilter");
  if (diffFilter && diffFilter.value === "custom_bloom") {
    distributeTotalIntoBloomMatrix(n);
  }
}

function onDifficultyFilterChange(val) {
  const box = document.getElementById("customBloomMatrix");
  if (!box) return;
  if (val === "custom_bloom") {
    box.style.display = "block";
    syncCustomBloomCounts();
  } else {
    box.style.display = "none";
  }
}

function distributeTotalIntoBloomMatrix(total) {
  const nb = Math.round(total * 0.3);
  const th = Math.round(total * 0.3);
  const vd = Math.round(total * 0.25);
  const vdc = Math.max(0, total - nb - th - vd);
  document.getElementById("bloomCountNB").value = nb;
  document.getElementById("bloomCountTH").value = th;
  document.getElementById("bloomCountVD").value = vd;
  document.getElementById("bloomCountVDC").value = vdc;
  updateBloomMatrixSummaryText(nb, th, vd, vdc);
}

function applyBloomPreset(nb, th, vd, vdc) {
  document.getElementById("bloomCountNB").value = nb;
  document.getElementById("bloomCountTH").value = th;
  document.getElementById("bloomCountVD").value = vd;
  document.getElementById("bloomCountVDC").value = vdc;
  syncCustomBloomCounts();
}

function syncCustomBloomCounts() {
  const nb = Math.max(0, parseInt(document.getElementById("bloomCountNB").value || "0"));
  const th = Math.max(0, parseInt(document.getElementById("bloomCountTH").value || "0"));
  const vd = Math.max(0, parseInt(document.getElementById("bloomCountVD").value || "0"));
  const vdc = Math.max(0, parseInt(document.getElementById("bloomCountVDC").value || "0"));
  const sum = Math.max(1, Math.min(50, nb + th + vd + vdc));

  document.getElementById("numQuestionCount").value = sum;
  document.getElementById("rangeQuestionCount").value = Math.min(30, sum);
  updateBloomMatrixSummaryText(nb, th, vd, vdc);
}

function updateBloomMatrixSummaryText(nb, th, vd, vdc) {
  const total = Math.max(1, nb + th + vd + vdc);
  const pNB = Math.round((nb / total) * 100);
  const pTH = Math.round((th / total) * 100);
  const pVD = Math.round((vd / total) * 100);
  const pVDC = Math.max(0, 100 - pNB - pTH - pVD);
  const el = document.getElementById("bloomMatrixSummary");
  if (el) {
    el.innerHTML = `Tổng cộng: <strong>${nb + th + vd + vdc} câu hỏi</strong> (Nhận biết: ${pNB}% • Thông hiểu: ${pTH}% • Vận dụng: ${pVD}% • Vận dụng cao: ${pVDC}%)`;
  }
}

function inferSubjectFromDocument(filename, contentText) {
  const combined = `${filename || ""} ${(contentText || "").slice(0, 1200)}`.toLowerCase();
  if (/môn\s*:\s*toán|toan[-_\s]|tam giác|mệnh đề|bất phương trình|hàm số|đạo hàm|tích phân|lượng giác/.test(combined)) {
    return "Toán học";
  }
  if (/vật\s*lý|vat[-_\s]*ly|cảm ứng điện từ|photon|dao động|dòng điện|quang học/.test(combined)) {
    return "Vật lý";
  }
  if (/hóa\s*học|hoa[-_\s]*hoc|phản ứng|nguyên tử|este|polime|oxi hóa/.test(combined)) {
    return "Hóa học";
  }
  if (/sinh\s*học|sinh[-_\s]*hoc|tế bào|dna|quang hợp|di truyền|ti thể/.test(combined)) {
    return "Sinh học";
  }
  if (/lịch\s*sử|lich[-_\s]*su|chiến thắng|hiệp định|cách mạng|thế chiến/.test(combined)) {
    return "Lịch sử";
  }
  if (/địa\s*lý|dia[-_\s]*ly|khí hậu|đồng bằng|dân cư|lãnh thổ/.test(combined)) {
    return "Địa lý";
  }
  if (/kinh\s*tế|kinh[-_\s]*te|gdp|lãi suất|lạm phát|cung cầu|tiền tệ/.test(combined)) {
    return "Kinh tế học";
  }
  if (/cơ\s*sở\s*dữ\s*liệu|database|sql|acid|b-tree|3nf/.test(combined)) {
    return "Hệ quản trị Cơ sở dữ liệu";
  }
  if (/transformer|qlora|lora|인공|mô hình ngôn ngữ|trí tuệ nhân tạo|ai/.test(combined)) {
    return "Trí tuệ nhân tạo";
  }
  return null;
}

async function extractTextFromPdfClientSide(file) {
  if (!window.pdfjsLib) return null;
  try {
    window.pdfjsLib.GlobalWorkerOptions.workerSrc =
      "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
    const arrayBuffer = await file.arrayBuffer();
    const pdf = await window.pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    const pageTexts = [];
    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      const textContent = await page.getTextContent();
      let pageStr = "";
      let lastX = null;
      let lastY = null;
      let lastWidth = 0;

      for (const item of textContent.items) {
        const s = item.str || "";
        if (!s) continue;
        const tx = item.transform ? item.transform[4] : null;
        const ty = item.transform ? item.transform[5] : null;
        const fontHeight = item.transform ? Math.abs(item.transform[0] || item.height || 10) : 10;

        if (lastY !== null && ty !== null && Math.abs(ty - lastY) > fontHeight * 0.65) {
          pageStr += "\n" + s;
        } else if (lastX !== null && tx !== null) {
          const gap = tx - (lastX + lastWidth);
          // Nếu khoảng cách giữa 2 mảnh ký tự rất sát nhau (< 22% cỡ chữ) thì nối liền không chèn dấu cách
          if (gap < fontHeight * 0.22 && gap > -fontHeight * 0.5) {
            pageStr += s;
          } else {
            pageStr += (pageStr.endsWith(" ") || s.startsWith(" ") ? "" : " ") + s;
          }
        } else {
          pageStr += s;
        }

        lastX = tx;
        lastY = ty;
        lastWidth = item.width || s.length * fontHeight * 0.45;
      }

      if (pageStr.trim()) {
        pageTexts.push(pageStr.trim());
      }
    }
    return pageTexts.join("\n\n");
  } catch (err) {
    console.warn("Trình đọc PDF phía trình duyệt chuyển sang bộ giải mã PDF phía Backend:", err);
    return null;
  }
}

async function handleFileUpload(inputElem) {
  if (!inputElem.files || !inputElem.files[0]) return;
  const file = inputElem.files[0];

  showToast(`Đang đọc và phân tích tài liệu "${file.name}"...`);

  let clientExtractedPdfText = null;
  if (file.name.toLowerCase().endsWith(".pdf")) {
    clientExtractedPdfText = await extractTextFromPdfClientSide(file);
  }

  const reader = new FileReader();
  reader.onload = async function (ev) {
    const base64Content = (ev.target.result || "").split(",")[1] || "";

    const res = await apiFetch("/api/documents/upload", {
      method: "POST",
      body: {
        filename: file.name,
        content_base64: base64Content,
        extracted_text_override: clientExtractedPdfText,
      },
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || "Không thể đọc tệp tài liệu.");
      return;
    }

    currentDocumentId = data.id;
    document.getElementById("genContextText").value = data.content;

    const cleanTitle = file.name.replace(/\.[^/.]+$/, "").replace(/[_\-]+/g, " ");
    document.getElementById("genExamTitle").value = `Đề kiểm tra: ${cleanTitle}`;
    const detectedSubj = inferSubjectFromDocument(file.name, data.content);
    if (detectedSubj) {
      document.getElementById("genSubject").value = detectedSubj;
    }

    const banner = document.getElementById("docStatsBanner");
    banner.style.display = "flex";
    document.getElementById("docStatsText").innerText =
      `Đã đọc (${data.file_type.toUpperCase()}): "${data.filename}" • ${data.word_count} từ • ${data.sentence_count} mệnh đề`;

    await loadSavedDocumentsDropdown();
    showToast(`Đã trích xuất ${data.word_count} từ từ tài liệu ${data.file_type.toUpperCase()}!`);
  };
  reader.readAsDataURL(file);
}

async function loadSavedDocumentsDropdown() {
  const res = await apiFetch("/api/documents");
  userDocumentsCache = await res.json();
  const sel = document.getElementById("savedDocsDropdown");
  sel.innerHTML =
    `<option value="">-- Chọn từ kho tài liệu đã đọc (${userDocumentsCache.length} tài liệu) --</option>` +
    userDocumentsCache
      .map((d) => `<option value="${d.id}">${escapeHtml(d.filename)} (${d.word_count} từ)</option>`)
      .join("");
}

function selectSavedDocument(docId) {
  if (!docId) return;
  const doc = userDocumentsCache.find((d) => String(d.id) === String(docId));
  if (!doc) return;
  currentDocumentId = doc.id;
  document.getElementById("genContextText").value = doc.content;
  const cleanTitle = (doc.filename || "").replace(/\.[^/.]+$/, "").replace(/[_\-]+/g, " ");
  if (cleanTitle) {
    document.getElementById("genExamTitle").value = `Đề kiểm tra: ${cleanTitle}`;
  }
  const detectedSubj = inferSubjectFromDocument(doc.filename, doc.content);
  if (detectedSubj) {
    document.getElementById("genSubject").value = detectedSubj;
  }
  const banner = document.getElementById("docStatsBanner");
  banner.style.display = "flex";
  document.getElementById("docStatsText").innerText =
    `Đang dùng tài liệu: "${doc.filename}" • ${doc.word_count} từ • ${doc.sentence_count} mệnh đề`;
  showToast(`Đã nạp nội dung tài liệu "${doc.filename}"`);
}

function getQuestionTypeMeta(qType) {
  const map = {
    multiple_choice: { label: "Trắc nghiệm", cls: "badge-type-mc" },
    fill_blank: { label: "Điền khuyết", cls: "badge-type-fb" },
    matching: { label: "Ghép cặp (A-B)", cls: "badge-type-mt" },
    essay: { label: "Tự luận (AI chấm)", cls: "badge-type-es" },
  };
  return map[qType] || map.multiple_choice;
}

function parseExtraData(q) {
  try {
    return JSON.parse(q.extra_data || "{}");
  } catch (e) {
    return {};
  }
}

function onQuestionTypeModeChange(modeVal) {
  const box = document.getElementById("customTypeCheckboxes");
  if (box) {
    box.style.display = modeVal === "custom" ? "grid" : "none";
  }
}

async function generateExamNow() {
  const btn = document.getElementById("btnRunGenerate");
  let totalQ = parseInt(document.getElementById("numQuestionCount").value || "5");
  const contextText = document.getElementById("genContextText").value.trim();

  if (contextText.split(/\s+/).length < 8) {
    alert("Vui lòng tải tài liệu lên hoặc nhập nội dung tài liệu tối thiểu 8 từ để AI sinh đề.");
    return;
  }

  const qTypeFilter = document.getElementById("genQuestionTypeFilter")
    ? document.getElementById("genQuestionTypeFilter").value
    : "mixed";

  let selectedTypes = null;
  if (qTypeFilter === "custom") {
    selectedTypes = Array.from(document.querySelectorAll(".qtype-cb:checked")).map((cb) => cb.value);
    if (!selectedTypes.length) {
      alert("Vui lòng tích chọn ít nhất 1 dạng câu hỏi muốn sinh.");
      return;
    }
  }

  const diffFilterVal = document.getElementById("genDifficultyFilter").value;
  let customCounts = null;
  if (diffFilterVal === "custom_bloom") {
    const nb = Math.max(0, parseInt(document.getElementById("bloomCountNB").value || "0"));
    const th = Math.max(0, parseInt(document.getElementById("bloomCountTH").value || "0"));
    const vd = Math.max(0, parseInt(document.getElementById("bloomCountVD").value || "0"));
    const vdc = Math.max(0, parseInt(document.getElementById("bloomCountVDC").value || "0"));
    if (nb + th + vd + vdc <= 0) {
      alert("Tổng số câu hỏi trong Ma trận Bloom phải lớn hơn 0.");
      return;
    }
    customCounts = {
      "Nhận biết": nb,
      "Thông hiểu": th,
      "Vận dụng": vd,
      "Vận dụng cao": vdc,
    };
    totalQ = nb + th + vd + vdc;
  }

  btn.disabled = true;
  btn.innerHTML = `<span>AI đang phân tích ngữ cảnh & sinh ${totalQ} câu hỏi...</span>`;

  try {
    const payload = {
      title: document.getElementById("genExamTitle").value.trim(),
      subject: document.getElementById("genSubject").value.trim(),
      exam_code: document.getElementById("genExamCode").value.trim(),
      duration_minutes: parseInt(document.getElementById("genDuration").value || "15"),
      total_questions: totalQ,
      difficulty_filter: diffFilterVal,
      custom_counts: customCounts,
      question_type_filter: qTypeFilter,
      selected_types: selectedTypes,
      context_text: contextText,
      document_id: currentDocumentId,
    };

    const res = await apiFetch("/api/exams/generate", {
      method: "POST",
      body: payload,
    });
    const exam = await res.json();
    if (!res.ok) {
      alert(exam.detail || "Có lỗi khi sinh bộ đề.");
      return;
    }

    renderActiveExam(exam);
    switchStudioStep("preview");
    showToast(`Đã sinh thành công ${exam.questions.length} câu hỏi và lưu vào tài khoản!`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `
      <svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
      <span>Sinh Bộ Đề Ngay & Chuyển Sang Bản Xem Trước</span>
    `;
  }
}

function renderQuestionContentForStudio(q) {
  const qType = q.question_type || "multiple_choice";
  const extra = parseExtraData(q);

  if (qType === "fill_blank") {
    return `
      <div class="fill-blank-box" style="margin-bottom:8px;">
        <div style="font-weight:700; color:#065f46; background:#ecfdf5; padding:8px 12px; border-radius:7px; border:1px solid #6ee7b7;">
          Đáp án chuẩn cần điền vào vị trí (1): <span style="text-decoration:underline;">${escapeHtml(q.correct_answer)}</span>
        </div>
      </div>
    `;
  }

  if (qType === "matching") {
    const colA = extra.col_a || [];
    const colB = extra.col_b || [];
    if (colA.length && colB.length) {
      return `
        <div class="matching-grid">
          <div class="matching-col">
            <div class="matching-col-title">CỘT A (Khái niệm / Thuật ngữ)</div>
            ${colA.map((item) => `<div class="matching-item"><strong>${escapeHtml(item.id)}.</strong> ${escapeHtml(item.text)}</div>`).join("")}
          </div>
          <div class="matching-col">
            <div class="matching-col-title">CỘT B (Nội dung mô tả / Định nghĩa)</div>
            ${colB.map((item) => `<div class="matching-item"><strong>${escapeHtml(item.id)}.</strong> ${escapeHtml(item.text)}</div>`).join("")}
          </div>
        </div>
        <div class="matching-answer-bar">
          <span>Đáp án ghép cặp chuẩn:</span>
          <span>${escapeHtml(q.correct_answer)}</span>
        </div>
      `;
    }
  }

  if (qType === "essay") {
    const kws = extra.rubric_keywords || [];
    const sampleAns = extra.sample_answer || q.correct_answer;
    return `
      <div class="essay-rubric-box">
        <div style="margin-bottom:8px;">
          <strong>Barem từ khóa trọng tâm (AI dùng để chấm điểm ngữ nghĩa):</strong>
          <div style="margin-top:6px;">
            ${kws.length ? kws.map((k) => `<span class="kw-chip">✓ ${escapeHtml(k)}</span>`).join("") : `<span>${escapeHtml(q.opt_b)}</span>`}
          </div>
        </div>
        <div style="background:#fff; padding:10px 12px; border-radius:8px; border:1px solid #fed7aa; color:#334155;">
          <strong>Đáp án mẫu chuẩn:</strong> ${escapeHtml(sampleAns)}
        </div>
      </div>
    `;
  }

  return `
    <div class="q-options">
      ${["A", "B", "C", "D"]
        .map((k) => {
          const optText = q["opt_" + k.toLowerCase()];
          const isAns = q.correct_answer === k;
          const shape = GAME_OPT_SHAPES[k] || "●";
          return `
          <div class="q-opt ${isAns ? "is-correct" : ""}">
            <span class="opt-key-badge opt-key-${k}">${shape} ${k}</span>
            <span>${escapeHtml(optText)} ${isAns ? " <strong>✓ (Đáp án đúng)</strong>" : ""}</span>
          </div>
        `;
        })
        .join("")}
    </div>
  `;
}

function renderActiveExam(exam) {
  currentActiveExam = exam;
  document.getElementById("activeExamHeaderTitle").innerText = exam.title;
  document.getElementById("activeExamHeaderMeta").innerHTML =
    `<div>Mã đề: <strong>${escapeHtml(exam.exam_code)}</strong> • Thời lượng: <strong>${exam.duration_minutes} phút</strong></div>` +
    `<div style="margin-top:3px;">Môn học: <strong>${escapeHtml(exam.subject)}</strong> • Tổng số: <strong>${exam.questions.length} câu hỏi</strong></div>`;

  const stepSub = document.getElementById("stepPreviewSubtext");
  if (stepSub) {
    stepSub.innerText = `Đang mở: [${exam.exam_code}] (${exam.questions.length} câu hỏi)`;
  }

  const qm = exam.quality_metrics || {};
  document.getElementById("qualityScoreBadge").innerText =
    `Chuẩn cấu trúc: ${qm.format_validity_rate || 100}% • Điểm chất lượng: ${qm.overall_quality_score || 100}%`;

  const listEl = document.getElementById("generatedQuestionsList");
  listEl.innerHTML = exam.questions
    .map((q, idx) => {
      const tMeta = getQuestionTypeMeta(q.question_type);
      return `
      <div class="q-card">
        <div class="q-card-top">
          <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
            <span class="badge ${getBloomBadge(q.difficulty)}">Câu ${q.question_order} • ${escapeHtml(q.difficulty)}</span>
            <span class="badge ${tMeta.cls}">${tMeta.label}</span>
          </div>
          <div style="display:flex; gap:6px; align-items:center;">
            <button class="btn btn-outline btn-xs" onclick="openEditQuestionModalByIndex(${idx})">
              Sửa câu hỏi
            </button>
            <button class="btn btn-danger btn-xs" onclick="deleteSingleQuestion(${q.id}, ${q.question_order})" title="Xóa câu hỏi này khỏi đề">
              Xóa
            </button>
          </div>
        </div>
        <div class="q-stem" style="white-space:pre-line;">${escapeHtml(q.question_text)}</div>
        ${renderQuestionContentForStudio(q)}
        <div class="q-exp">
          <strong>Giải thích & Căn cứ tài liệu:</strong> ${escapeHtml(q.explanation)}
        </div>
      </div>
    `;
    })
    .join("");
}

function openEditQuestionModalByIndex(idx) {
  if (!currentActiveExam || !currentActiveExam.questions[idx]) return;
  openEditQuestionModal(currentActiveExam.questions[idx]);
}

async function deleteSingleQuestion(questionId, orderNum) {
  if (!currentActiveExam) return;
  if (currentActiveExam.questions.length <= 1) {
    alert("Bộ đề phải có tối thiểu 1 câu hỏi. Không thể xóa câu cuối cùng.");
    return;
  }
  if (!confirm(`Bạn có chắc chắn muốn xóa Câu ${orderNum} khỏi bộ đề này?`)) return;

  const res = await apiFetch(`/api/questions/${questionId}`, { method: "DELETE" });
  const data = await res.json();
  if (!res.ok) {
    alert(data.detail || "Không thể xóa câu hỏi.");
    return;
  }
  renderActiveExam(data);
  showToast(`Đã xóa Câu ${orderNum} và đánh lại số thứ tự bộ đề!`);
}

async function shuffleCurrentExam() {
  if (!currentActiveExam) return;
  const btn = document.getElementById("btnShuffleExam");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span>Đang trộn câu hỏi & đảo đáp án...</span>`;
  }
  try {
    const res = await apiFetch(`/api/exams/${currentActiveExam.id}/shuffle`, {
      method: "POST",
      body: {},
    });
    const newExam = await res.json();
    if (!res.ok) {
      alert(newExam.detail || "Không thể trộn đề.");
      return;
    }
    renderActiveExam(newExam);
    showToast(`Đã tạo mã đề trộn mới [${newExam.exam_code}] và lưu vào kho đề!`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `
        <svg class="svg-icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/><polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/><line x1="4" y1="4" x2="9" y2="9"/></svg>
        <span>🔀 Trộn Đề / Tạo Mã Đề Mới</span>
      `;
    }
  }
}

function exportCurrentExam(formatType) {
  if (!currentActiveExam) return;
  const url = `/api/exams/${currentActiveExam.id}/export?format=${formatType}&token=${encodeURIComponent(authToken)}`;
  window.location.href = url;
  showToast(`Đang tải xuống bộ đề (${formatType.toUpperCase()})...`);
}

/* =========================================================================
   4. MODAL CHỈNH SỬA / THÊM MỚI CÂU HỎI ĐỘNG THEO TỪNG DẠNG THỨC & KHO BỘ ĐỀ
========================================================================= */
function applyModalTypeLayout(qType, fillSampleDefaults = false) {
  const tMeta = getQuestionTypeMeta(qType);
  const typeBadge = document.getElementById("modalTypeBadge");
  if (typeBadge) {
    typeBadge.className = `badge ${tMeta.cls}`;
    typeBadge.innerText = tMeta.label;
  }

  const ansLabel = document.getElementById("modalCorrectAnswerLabel");
  const optALabel = document.getElementById("modalOptALabel");
  const optBLabel = document.getElementById("modalOptBLabel");
  const optCLabel = document.getElementById("modalOptCLabel");
  const optDLabel = document.getElementById("modalOptDLabel");
  const rowAB = document.getElementById("modalRowAB");
  const rowCD = document.getElementById("modalRowCD");

  if (qType === "fill_blank") {
    ansLabel.innerText = "Đáp án / Từ khóa cần điền vào vị trí trống (1)";
    if (rowAB) rowAB.style.display = "none";
    if (rowCD) rowCD.style.display = "none";
    if (fillSampleDefaults) {
      document.getElementById("modalQuestionText").value =
        "[Điền khuyết] Điền thuật ngữ hoặc kết quả chính xác vào vị trí trống (1) trong câu sau:\n« Mô hình ngôn ngữ lớn sử dụng cơ chế [ (1) ................ ] để xử lý song song chuỗi văn bản. »";
      document.getElementById("modalCorrectAnswer").value = "Self-Attention";
      document.getElementById("modalOptA").value = "";
      document.getElementById("modalOptB").value = "Đáp án chuẩn: Self-Attention";
      document.getElementById("modalOptC").value = "";
      document.getElementById("modalOptD").value = "";
      document.getElementById("modalExplanation").value = "Cơ chế Self-Attention là thành phần cốt lõi của kiến trúc Transformer.";
    }
  } else if (qType === "matching") {
    ansLabel.innerText = "Đáp án ghép cặp chuẩn (VD: 1-B, 2-A, 3-D, 4-C)";
    optALabel.innerText = "Cặp ghép 1 (Cột A ⟷ Cột B)";
    optBLabel.innerText = "Cặp ghép 2 (Cột A ⟷ Cột B)";
    optCLabel.innerText = "Cặp ghép 3 (Cột A ⟷ Cột B)";
    optDLabel.innerText = "Cặp ghép 4 (Cột A ⟷ Cột B)";
    if (rowAB) rowAB.style.display = "grid";
    if (rowCD) rowCD.style.display = "grid";
    if (fillSampleDefaults) {
      document.getElementById("modalQuestionText").value =
        "[Ghép cặp] Hãy nối mỗi khái niệm ở Cột A (1, 2, 3, 4) với mô tả đúng nhất ở Cột B (A, B, C, D):";
      document.getElementById("modalCorrectAnswer").value = "1-B, 2-A, 3-D, 4-C";
      document.getElementById("modalOptA").value = "1. Transformer ⟷ B. Kiến trúc mạng nơ-ron dựa trên cơ chế Self-Attention";
      document.getElementById("modalOptB").value = "2. LoRA ⟷ A. Phân rã ma trận hạng thấp giúp giảm tham số tinh chỉnh";
      document.getElementById("modalOptC").value = "3. QLoRA ⟷ D. Lượng tử hóa 4-bit NormalFloat tiết kiệm bộ nhớ VRAM";
      document.getElementById("modalOptD").value = "4. Thang đo Bloom ⟷ C. Phân loại mức độ nhận thức từ Nhận biết đến Vận dụng cao";
      document.getElementById("modalExplanation").value = "Ghép đúng từng thuật ngữ ở Cột A với định nghĩa tương ứng ở Cột B.";
    }
  } else if (qType === "essay") {
    ansLabel.innerText = "Đáp án mẫu chuẩn (Dùng để chấm điểm ngữ nghĩa)";
    optALabel.innerText = "Hướng dẫn chấm & Yêu cầu trình bày";
    optBLabel.innerText = "Từ khóa chấm điểm (Rubric Keywords, cách nhau dấu phẩy)";
    if (rowAB) rowAB.style.display = "grid";
    if (rowCD) rowCD.style.display = "none";
    if (fillSampleDefaults) {
      document.getElementById("modalQuestionText").value =
        "[Tự luận] Hãy phân tích vai trò của kỹ thuật QLoRA trong quá trình tinh chỉnh mô hình ngôn ngữ lớn?";
      document.getElementById("modalCorrectAnswer").value =
        "Kỹ thuật QLoRA lượng tử hóa trọng số gốc xuống 4-bit NormalFloat (NF4) kết hợp ma trận hạng thấp LoRA giúp tiết kiệm tối đa bộ nhớ VRAM khi huấn luyện.";
      document.getElementById("modalOptA").value = "Trình bày rõ cơ chế NF4 và lợi ích tiết kiệm VRAM.";
      document.getElementById("modalOptB").value = "Từ khóa chấm điểm (Rubric Keywords): QLoRA, 4-bit NormalFloat, LoRA, tiết kiệm VRAM";
      document.getElementById("modalOptC").value = "";
      document.getElementById("modalOptD").value = "";
      document.getElementById("modalExplanation").value = "Chấm tự động dựa trên độ tương đồng ngữ nghĩa TF-IDF và từ khóa Rubric.";
    }
  } else {
    ansLabel.innerText = "Đáp án đúng (A, B, C hoặc D)";
    optALabel.innerText = "Phương án A";
    optBLabel.innerText = "Phương án B";
    optCLabel.innerText = "Phương án C";
    optDLabel.innerText = "Phương án D";
    if (rowAB) rowAB.style.display = "grid";
    if (rowCD) rowCD.style.display = "grid";
    if (fillSampleDefaults) {
      document.getElementById("modalQuestionText").value = "";
      document.getElementById("modalCorrectAnswer").value = "A";
      document.getElementById("modalOptA").value = "";
      document.getElementById("modalOptB").value = "";
      document.getElementById("modalOptC").value = "";
      document.getElementById("modalOptD").value = "";
      document.getElementById("modalExplanation").value = "";
    }
  }
}

function openAddQuestionModal() {
  if (!currentActiveExam) return;
  document.getElementById("modalQuestionId").value = "";
  const headerTitle = document.getElementById("modalHeaderTitle");
  if (headerTitle) headerTitle.innerText = "Thêm Câu Hỏi Mới Vào Bộ Đề";
  const submitBtn = document.getElementById("modalSubmitBtn");
  if (submitBtn) submitBtn.innerText = "+ Thêm Câu Hỏi";

  const typeWrap = document.getElementById("modalQuestionTypeWrap");
  if (typeWrap) typeWrap.style.display = "block";
  const typeSelect = document.getElementById("modalQuestionTypeSelect");
  if (typeSelect) typeSelect.value = "multiple_choice";

  document.getElementById("modalDifficulty").value = "Thông hiểu";
  applyModalTypeLayout("multiple_choice", true);
  document.getElementById("editQuestionModal").classList.add("show");
}

function openEditQuestionModal(q) {
  document.getElementById("modalQuestionId").value = q.id;
  const headerTitle = document.getElementById("modalHeaderTitle");
  if (headerTitle) headerTitle.innerText = `Chỉnh Sửa Câu Hỏi Số ${q.question_order}`;
  const submitBtn = document.getElementById("modalSubmitBtn");
  if (submitBtn) submitBtn.innerText = "Lưu Thay Đổi";

  const typeWrap = document.getElementById("modalQuestionTypeWrap");
  if (typeWrap) typeWrap.style.display = "none";

  const qType = q.question_type || "multiple_choice";
  applyModalTypeLayout(qType, false);

  document.getElementById("modalDifficulty").value = q.difficulty;
  document.getElementById("modalCorrectAnswer").value = q.correct_answer;
  document.getElementById("modalQuestionText").value = q.question_text;
  document.getElementById("modalOptA").value = q.opt_a || "";
  document.getElementById("modalOptB").value = q.opt_b || "";
  document.getElementById("modalOptC").value = q.opt_c || "";
  document.getElementById("modalOptD").value = q.opt_d || "";
  document.getElementById("modalExplanation").value = q.explanation || "";

  document.getElementById("editQuestionModal").classList.add("show");
}

function closeEditQuestionModal() {
  document.getElementById("editQuestionModal").classList.remove("show");
}

async function saveQuestionChanges() {
  if (!currentActiveExam) return;
  const qid = document.getElementById("modalQuestionId").value;
  const qText = document.getElementById("modalQuestionText").value.trim();
  if (!qText) {
    alert("Vui lòng nhập nội dung câu hỏi.");
    return;
  }

  const payload = {
    difficulty: document.getElementById("modalDifficulty").value,
    correct_answer: document.getElementById("modalCorrectAnswer").value,
    question_text: qText,
    opt_a: document.getElementById("modalOptA").value,
    opt_b: document.getElementById("modalOptB").value,
    opt_c: document.getElementById("modalOptC").value,
    opt_d: document.getElementById("modalOptD").value,
    explanation: document.getElementById("modalExplanation").value,
  };

  if (!qid) {
    // Chế độ thêm câu hỏi mới
    payload.question_type = document.getElementById("modalQuestionTypeSelect").value || "multiple_choice";
    const res = await apiFetch(`/api/exams/${currentActiveExam.id}/questions`, {
      method: "POST",
      body: payload,
    });
    const updatedExam = await res.json();
    if (!res.ok) {
      alert(updatedExam.detail || "Có lỗi khi thêm câu hỏi.");
      return;
    }
    closeEditQuestionModal();
    renderActiveExam(updatedExam);
    showToast(`Đã thêm câu hỏi số ${updatedExam.questions.length} vào bộ đề!`);
    return;
  }

  const res = await apiFetch(`/api/questions/${qid}`, {
    method: "PUT",
    body: payload,
  });
  if (res.ok && currentActiveExam) {
    closeEditQuestionModal();
    const updated = await (await apiFetch(`/api/exams/${currentActiveExam.id}`)).json();
    renderActiveExam(updated);
    showToast("Đã cập nhật câu hỏi thành công!");
  }
}

async function loadMySavedExams() {
  const res = await apiFetch("/api/exams");
  allUserExams = await res.json();
  renderMyExamsTable(allUserExams);
}

function filterMyExamsTable() {
  const kw = document.getElementById("searchMyExamsInput").value.toLowerCase().trim();
  const filtered = allUserExams.filter(
    (e) =>
      e.title.toLowerCase().includes(kw) ||
      e.subject.toLowerCase().includes(kw) ||
      e.exam_code.toLowerCase().includes(kw)
  );
  renderMyExamsTable(filtered);
}

function renderMyExamsTable(exams) {
  const tbody = document.getElementById("myExamsTableBody");
  if (!exams.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:32px; color:var(--text-muted);">Chưa có bộ đề nào phù hợp.</td></tr>`;
    return;
  }

  tbody.innerHTML = exams
    .map((ex) => {
      const bloomBadges = Object.entries(ex.bloom_summary || {})
        .map(([k, v]) => `<span class="badge ${getBloomBadge(k)}" style="margin-right:4px; margin-bottom:3px;">${escapeHtml(k)}: ${v}</span>`)
        .join("");
      const typeBadges = Object.entries(ex.type_summary || {})
        .map(([k, v]) => {
          const tm = getQuestionTypeMeta(k);
          return `<span class="badge ${tm.cls}" style="margin-right:4px; margin-bottom:3px;">${tm.label}: ${v}</span>`;
        })
        .join("");
      return `
      <tr>
        <td><code>${escapeHtml(ex.exam_code)}</code></td>
        <td>
          <div style="font-weight:700; color:var(--text-dark); margin-bottom:3px;">${escapeHtml(ex.title)}</div>
          <span class="badge badge-purple">${escapeHtml(ex.subject)}</span>
        </td>
        <td>
          <div style="font-weight:700; margin-bottom:4px;">${ex.total_questions} câu hỏi (${ex.duration_minutes} phút)</div>
          <div>${typeBadges}</div>
        </td>
        <td>${bloomBadges}</td>
        <td style="font-size:12px; color:var(--text-muted);">${ex.created_at}</td>
        <td>
          <div style="display:flex; flex-wrap:wrap; gap:6px;">
            <button class="btn btn-primary btn-xs" onclick="openSavedExamInStudio(${ex.id})">Mở đề</button>
            <button class="btn btn-outline btn-xs" onclick="openSavedExamInQuiz(${ex.id})">Thi thử</button>
            <a href="/api/exams/${ex.id}/export?format=docx_full&token=${encodeURIComponent(authToken)}" class="btn btn-emerald btn-xs">Word</a>
            <button class="btn btn-outline btn-xs" onclick="contributeExamToAI(${ex.id})" title="Đóng góp vào Dataset huấn luyện AI">+Train</button>
            <button class="btn btn-danger btn-xs" onclick="deleteSavedExam(${ex.id})">Xóa</button>
          </div>
        </td>
      </tr>
    `;
    })
    .join("");
}

async function openSavedExamInStudio(examId) {
  const exam = await (await apiFetch(`/api/exams/${examId}`)).json();
  renderActiveExam(exam);
  openTab("generate", document.querySelectorAll(".nav-item")[0]);
  switchStudioStep("preview");
}

async function deleteSavedExam(examId) {
  if (!confirm("Bạn có chắc chắn muốn xóa bộ đề này khỏi tài khoản?")) return;
  await apiFetch(`/api/exams/${examId}`, { method: "DELETE" });
  showToast("Đã xóa bộ đề khỏi tài khoản.");
  loadMySavedExams();
}

async function contributeExamToAI(examId) {
  const res = await apiFetch(`/api/training/contribute/${examId}`, { method: "POST" });
  const data = await res.json();
  if (res.ok) {
    showToast(`Đã bổ sung ${data.added_samples} mẫu câu hỏi vào tập dữ liệu huấn luyện AI!`);
  }
}

/* =========================================================================
   5. PHÒNG THI THỬ KHÔNG GIẬT DOM & BẢNG PHÂN TÍCH NĂNG LỰC BLOOM
========================================================================= */
function startQuizFromCurrentExam() {
  if (!currentActiveExam) return;
  openSavedExamInQuiz(currentActiveExam.id);
}

async function openSavedExamInQuiz(examId) {
  openTab("quiz", document.querySelectorAll(".nav-item")[2]);
  await setupQuizSelector(examId);
}

async function setupQuizSelector(targetExamId = null) {
  const res = await apiFetch("/api/exams");
  allUserExams = await res.json();
  const sel = document.getElementById("quizExamSelect");
  sel.innerHTML = allUserExams.map((e) => `<option value="${e.id}">[${escapeHtml(e.exam_code)}] ${escapeHtml(e.title)}</option>`).join("");
  const chosenId = targetExamId || (allUserExams[0] && allUserExams[0].id);
  if (chosenId) {
    sel.value = chosenId;
    loadExamForQuiz(chosenId);
  }
}

async function loadExamForQuiz(examId) {
  const res = await apiFetch(`/api/exams/${examId}`);
  quizExamData = await res.json();
  quizAnswers = {};

  document.getElementById("quizTitleDisplay").innerText = quizExamData.title;
  document.getElementById("quizMetaDisplay").innerText =
    `Mã đề: ${quizExamData.exam_code} • Môn: ${quizExamData.subject} • Số lượng: ${quizExamData.questions.length} câu`;
  document.getElementById("quizScoreBanner").style.display = "none";
  document.getElementById("btnSubmitQuiz").disabled = false;

  clearInterval(quizTimer);
  quizRemainingSec = (quizExamData.duration_minutes || 15) * 60;
  quizElapsedSec = 0;
  updateQuizTimerUI();
  quizTimer = setInterval(() => {
    quizRemainingSec--;
    quizElapsedSec++;
    updateQuizTimerUI();
    if (quizRemainingSec <= 0) {
      clearInterval(quizTimer);
      submitQuizNow(true);
    }
  }, 1000);

  renderQuizQuestions();
}

function updateQuizTimerUI() {
  const m = String(Math.floor(Math.max(0, quizRemainingSec) / 60)).padStart(2, "0");
  const s = String(Math.max(0, quizRemainingSec) % 60).padStart(2, "0");
  document.getElementById("quizTimerBox").innerText = `${m}:${s}`;
}

function renderQuizInputByQuestionType(q) {
  const qType = q.question_type || "multiple_choice";
  const extra = parseExtraData(q);
  const currentVal = quizAnswers[q.id] || "";

  if (qType === "fill_blank") {
    return `
      <div class="fill-blank-box">
        <label style="color:#9d174d;">Nhập kết quả / từ khóa cần điền vào vị trí trống (1):</label>
        <input
          type="text"
          value="${escapeHtml(currentVal)}"
          placeholder="Nhập đáp án của bạn tại đây..."
          oninput="updateTextQuizAnswer(${q.id}, this.value)"
        />
      </div>
    `;
  }

  if (qType === "matching") {
    const colA = extra.col_a || [
      { id: "1", text: "Mục 1" },
      { id: "2", text: "Mục 2" },
      { id: "3", text: "Mục 3" },
      { id: "4", text: "Mục 4" },
    ];
    const colB = extra.col_b || [];

    const curMap = {};
    currentVal.split(",").forEach((p) => {
      if (p.includes("-")) {
        const [k, v] = p.trim().split("-");
        curMap[k.trim()] = v.trim();
      }
    });

    return `
      <div class="matching-grid">
        <div class="matching-col">
          <div class="matching-col-title">CỘT A (Khái niệm 1, 2, 3, 4)</div>
          ${colA.map((item) => `<div class="matching-item"><strong>${escapeHtml(item.id)}.</strong> ${escapeHtml(item.text)}</div>`).join("")}
        </div>
        <div class="matching-col">
          <div class="matching-col-title">CỘT B (Nội dung A, B, C, D)</div>
          ${colB.map((item) => `<div class="matching-item"><strong>${escapeHtml(item.id)}.</strong> ${escapeHtml(item.text)}</div>`).join("")}
        </div>
      </div>
      <div class="matching-quiz-selectors">
        ${["1", "2", "3", "4"]
          .map(
            (numKey) => `
          <div>
            <label style="font-size:12px; margin-bottom:4px;">Nối mục ${numKey} với:</label>
            <select onchange="updateMatchingPairAnswer(${q.id}, '${numKey}', this.value)">
              <option value="">-- Chọn --</option>
              ${["A", "B", "C", "D"]
                .map((letter) => `<option value="${letter}" ${curMap[numKey] === letter ? "selected" : ""}>Ý ${letter}</option>`)
                .join("")}
            </select>
          </div>
        `
          )
          .join("")}
      </div>
    `;
  }

  if (qType === "essay") {
    return `
      <div class="essay-rubric-box">
        <div style="margin-bottom:6px; font-size:12.5px;">
          <strong>Chấm điểm Tự luận bằng AI:</strong> Hệ thống đo độ tương đồng ngữ nghĩa (TF-IDF Cosine Similarity) và đối chiếu các ý chính trong Barem.
        </div>
        <textarea
          rows="4"
          placeholder="Nhập câu trả lời tự luận của bạn vào đây (nêu rõ khái niệm, cơ chế hoạt động và ý nghĩa theo tài liệu)..."
          oninput="updateTextQuizAnswer(${q.id}, this.value)"
        >${escapeHtml(currentVal)}</textarea>
      </div>
    `;
  }

  return `
    <div class="q-options" id="quiz-opts-${q.id}">
      ${["A", "B", "C", "D"]
        .map((k) => {
          const chosen = currentVal === k;
          const shape = GAME_OPT_SHAPES[k] || "●";
          return `
          <div class="q-opt ${chosen ? "is-selected" : ""}" data-opt="${k}" style="cursor:pointer;" onclick="selectQuizOption(${q.id}, '${k}')">
            <input type="radio" name="quiz_${q.id}" value="${k}" ${chosen ? "checked" : ""} style="display:none;" />
            <span class="opt-key-badge opt-key-${k}">${shape} ${k}</span>
            <span>${escapeHtml(q["opt_" + k.toLowerCase()])}</span>
          </div>
        `;
        })
        .join("")}
    </div>
  `;
}

function renderQuizQuestions() {
  const container = document.getElementById("quizQuestionsContainer");
  container.innerHTML = quizExamData.questions
    .map((q) => {
      const tMeta = getQuestionTypeMeta(q.question_type);
      return `
      <div class="q-card" id="quiz-q-${q.id}">
        <div class="q-card-top">
          <div style="display:flex; gap:6px; align-items:center;">
            <span class="badge ${getBloomBadge(q.difficulty)}">Câu ${q.question_order} • ${escapeHtml(q.difficulty)}</span>
            <span class="badge ${tMeta.cls}">${tMeta.label}</span>
          </div>
        </div>
        <div class="q-stem" style="white-space:pre-line;">${escapeHtml(q.question_text)}</div>
        ${renderQuizInputByQuestionType(q)}
        <div id="quiz-feedback-${q.id}"></div>
      </div>
    `;
    })
    .join("");

  updateQuizPaletteUI();
}

function updateQuizPaletteUI() {
  const pal = document.getElementById("quizPaletteGrid");
  if (!pal || !quizExamData) return;

  let answeredCount = 0;
  pal.innerHTML = quizExamData.questions
    .map((q) => {
      const ans = (quizAnswers[q.id] || "").trim();
      if (ans) answeredCount++;
      const shortBadge = ans.length > 3 ? "✓" : ans;
      return `
      <button class="btn ${ans ? "btn-primary" : "btn-outline"}" style="padding:7px 0; font-size:12px;" onclick="document.getElementById('quiz-q-${q.id}').scrollIntoView({behavior:'smooth'})">
        ${q.question_order}${shortBadge ? ":" + shortBadge : ""}
      </button>
    `;
    })
    .join("");

  const counterEl = document.getElementById("quizAnsweredCounter");
  if (counterEl) {
    counterEl.innerText = `Đã trả lời: ${answeredCount} / ${quizExamData.questions.length} câu hỏi`;
  }
}

function selectQuizOption(qId, optKey) {
  quizAnswers[qId] = optKey;
  const optsBox = document.getElementById(`quiz-opts-${qId}`);
  if (optsBox) {
    optsBox.querySelectorAll(".q-opt").forEach((el) => {
      const isMatch = el.getAttribute("data-opt") === optKey;
      el.classList.toggle("is-selected", isMatch);
      const radio = el.querySelector('input[type="radio"]');
      if (radio) radio.checked = isMatch;
    });
  }
  updateQuizPaletteUI();
}

function updateTextQuizAnswer(qId, val) {
  quizAnswers[qId] = val;
  updateQuizPaletteUI();
}

function updateMatchingPairAnswer(qId, numKey, letterVal) {
  const curStr = quizAnswers[qId] || "";
  const curMap = {};
  curStr.split(",").forEach((p) => {
    if (p.includes("-")) {
      const [k, v] = p.trim().split("-");
      if (k && v) curMap[k.trim()] = v.trim();
    }
  });
  if (letterVal) {
    curMap[numKey] = letterVal;
  } else {
    delete curMap[numKey];
  }
  const pairs = ["1", "2", "3", "4"]
    .filter((k) => curMap[k])
    .map((k) => `${k}-${curMap[k]}`);
  quizAnswers[qId] = pairs.join(", ");
  updateQuizPaletteUI();
}

async function submitQuizNow(forceSubmit = false) {
  if (!quizExamData) return;

  if (!forceSubmit) {
    const totalQ = quizExamData.questions.length;
    const answeredQ = quizExamData.questions.filter((q) => (quizAnswers[q.id] || "").trim().length > 0).length;
    if (answeredQ < totalQ) {
      const unanswered = totalQ - answeredQ;
      if (!confirm(`Bạn còn ${unanswered}/${totalQ} câu hỏi chưa làm. Bạn có chắc chắn muốn nộp bài ngay không?`)) {
        return;
      }
    }
  }

  clearInterval(quizTimer);
  document.getElementById("btnSubmitQuiz").disabled = true;

  const res = await apiFetch(`/api/exams/${quizExamData.id}/attempt`, {
    method: "POST",
    body: {
      time_spent_sec: quizElapsedSec,
      answers: quizAnswers,
    },
  });
  const result = await res.json();

  const bloomEntries = Object.entries(result.bloom_breakdown || {});
  const typeEntries = Object.entries(result.type_breakdown || {});

  const bloomBarsHtml = bloomEntries
    .map(([diff, stat]) => {
      const pct = stat.total > 0 ? Math.round((stat.earned / stat.total) * 100) : 0;
      return `
        <div class="comp-row">
          <div class="comp-row-top">
            <span>${escapeHtml(diff)}</span>
            <span>${stat.earned}/${stat.total} câu (${pct}%)</span>
          </div>
          <div class="comp-bar-track">
            <div class="comp-bar-fill" style="width:${pct}%;"></div>
          </div>
        </div>
      `;
    })
    .join("");

  const typeBarsHtml = typeEntries
    .map(([qt, stat]) => {
      const tm = getQuestionTypeMeta(qt);
      const pct = stat.total > 0 ? Math.round((stat.earned / stat.total) * 100) : 0;
      return `
        <div class="comp-row">
          <div class="comp-row-top">
            <span>${tm.label}</span>
            <span>${stat.earned}/${stat.total} câu (${pct}%)</span>
          </div>
          <div class="comp-bar-track">
            <div class="comp-bar-fill" style="width:${pct}%; background:var(--emerald);"></div>
          </div>
        </div>
      `;
    })
    .join("");

  const banner = document.getElementById("quizScoreBanner");
  banner.style.display = "block";
  banner.innerHTML = `
    <div class="card" style="background:var(--emerald-light); border-color:#6ee7b7; margin-bottom:0;">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
        <div>
          <div style="font-size:18px; font-weight:800; color:#065f46;">
            ĐIỂM SỐ CỦA BẠN: ${result.score} / 10.0 ĐIỂM (Đạt yêu cầu ${result.correct_count}/${result.total_questions} câu)
          </div>
          <div style="font-size:12.5px; color:#047857; margin-top:4px;">
            Thời gian hoàn thành: ${result.time_spent_sec} giây • Đã chấm tự động cả Trắc nghiệm, Điền khuyết, Ghép cặp & Tự luận!
          </div>
        </div>
        <button class="btn btn-primary" onclick="loadExamForQuiz(${quizExamData.id})">Làm lại đề này</button>
      </div>
      <div class="competency-grid">
        <div class="comp-card">
          <div class="comp-card-title">Phân tích năng lực theo Thang đo Bloom</div>
          ${bloomBarsHtml || "<div>Không có dữ liệu</div>"}
        </div>
        <div class="comp-card">
          <div class="comp-card-title">Độ chính xác theo 4 dạng câu hỏi</div>
          ${typeBarsHtml || "<div>Không có dữ liệu</div>"}
        </div>
      </div>
    </div>
  `;

  result.details.forEach((d) => {
    const fb = document.getElementById(`quiz-feedback-${d.question_id}`);
    if (!fb) return;
    const ptsPercent = Math.round((d.points_earned || 0) * 100);
    fb.innerHTML = `
      <div class="q-exp" style="background:${d.is_correct ? "#f0fdf4" : "#fef2f2"}; border-left-color:${d.is_correct ? "#059669" : "#dc2626"}; color:${d.is_correct ? "#166534" : "#991b1b"};">
        <strong>${d.is_correct ? `Đạt ${ptsPercent}% điểm câu!` : `Chưa đạt (${ptsPercent}% điểm câu — Bài làm: ${escapeHtml(d.user_choice)})`}</strong><br/>
        ${escapeHtml(d.explanation)}
      </div>
    `;
  });

  banner.scrollIntoView({ behavior: "smooth" });
}

/* =========================================================================
   6. LỊCH SỬ TÀI KHOẢN, KHO TÀI LIỆU & QUY TRÌNH HUẤN LUYỆN AI
========================================================================= */
async function loadHistoryAndDocuments() {
  const [histRes, docsRes] = await Promise.all([apiFetch("/api/history"), apiFetch("/api/documents")]);
  const histData = await histRes.json();
  userDocumentsCache = await docsRes.json();

  document.getElementById("statExamsCount").innerText = histData.summary.total_exams;
  document.getElementById("statQuestionsCount").innerText = histData.summary.total_questions;
  document.getElementById("statDocsCount").innerText = histData.summary.total_documents;
  document.getElementById("statAttemptsCount").innerText = histData.summary.total_attempts;

  const docsBody = document.getElementById("historyDocsBody");
  docsBody.innerHTML = userDocumentsCache.length
    ? userDocumentsCache
        .map(
          (d) => `
    <tr>
      <td><strong>${escapeHtml(d.filename)}</strong></td>
      <td><span class="badge badge-nb">${escapeHtml(d.file_type)}</span></td>
      <td>${d.word_count} từ (${d.sentence_count} câu)</td>
      <td style="font-size:12px; color:var(--text-muted);">${d.created_at}</td>
      <td>
        <div style="display:flex; gap:6px; flex-wrap:wrap;">
          <button class="btn btn-primary btn-xs" onclick="reuseDocumentForGeneration(${d.id})">
            Dùng sinh đề
          </button>
          <button class="btn btn-danger btn-xs" onclick="deleteSavedDocument(${d.id})">
            Xóa
          </button>
        </div>
      </td>
    </tr>
  `
        )
        .join("")
    : `<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:20px;">Chưa có tài liệu nào trong kho lưu trữ.</td></tr>`;

  const attBody = document.getElementById("historyAttemptsBody");
  attBody.innerHTML = (histData.quiz_attempts || []).length
    ? histData.quiz_attempts
        .map(
          (a) => `
      <tr>
        <td><strong>[${escapeHtml(a.exam_code)}]</strong> ${escapeHtml(a.exam_title)}</td>
        <td><strong style="color:var(--emerald);">${a.score} / 10</strong></td>
        <td>${a.correct_count}/${a.total_questions} câu</td>
        <td style="font-size:12px; color:var(--text-muted);">${a.created_at}</td>
        <td>
          <button class="btn btn-outline btn-xs" onclick="viewAttemptDetail(${a.id})">
            Xem chi tiết
          </button>
        </td>
      </tr>
    `
        )
        .join("")
    : `<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:20px;">Chưa có lượt làm bài thi thử nào.</td></tr>`;

  const timeline = document.getElementById("activityTimelineBox");
  timeline.innerHTML = (histData.activities || [])
    .map(
      (act) => `
    <div style="padding:10px 12px; border-bottom:1px solid var(--border); font-size:13px;">
      <div style="display:flex; justify-content:space-between; gap:8px;">
        <strong>${escapeHtml(act.description)}</strong>
        <span style="font-size:11.5px; color:var(--text-muted); white-space:nowrap;">${act.created_at}</span>
      </div>
    </div>
  `
    )
    .join("");
}

function reuseDocumentForGeneration(docId) {
  selectSavedDocument(docId);
  openTab("generate", document.querySelectorAll(".nav-item")[0]);
  switchStudioStep("config");
}

async function deleteSavedDocument(docId) {
  if (!confirm("Bạn có chắc chắn muốn xóa tài liệu này khỏi kho lưu trữ?")) return;
  const res = await apiFetch(`/api/documents/${docId}`, { method: "DELETE" });
  if (res.ok) {
    showToast("Đã xóa tài liệu khỏi kho lưu trữ.");
    loadHistoryAndDocuments();
    loadUserDocumentsDropdown();
  }
}

async function viewAttemptDetail(attemptId) {
  const res = await apiFetch(`/api/attempts/${attemptId}`);
  const data = await res.json();
  if (!res.ok) {
    alert(data.detail || "Không thể tải chi tiết bài làm.");
    return;
  }

  document.getElementById("attemptModalTitle").innerText = `[${data.exam_code}] ${data.exam_title}`;
  document.getElementById("attemptModalMeta").innerText =
    `Điểm số: ${data.score}/10 (${data.correct_count}/${data.total_questions} câu đạt) • Thời gian làm: ${data.time_spent_sec} giây • Ngày nộp: ${data.created_at}`;

  const bodyEl = document.getElementById("attemptModalBody");
  bodyEl.innerHTML = (data.details || [])
    .map((d) => {
      const tMeta = getQuestionTypeMeta(d.question_type);
      const ptsPct = Math.round((d.points_earned || 0) * 100);
      return `
        <div class="q-card" style="padding:14px 16px; margin-bottom:12px;">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:8px; flex-wrap:wrap;">
            <div style="display:flex; gap:6px; align-items:center;">
              <span class="badge ${getBloomBadge(d.difficulty)}">Câu ${d.question_order} • ${escapeHtml(d.difficulty)}</span>
              <span class="badge ${tMeta.cls}">${tMeta.label}</span>
            </div>
            <span class="badge ${d.is_correct ? "badge-nb" : "badge-vdc"}">
              ${d.is_correct ? `✓ Đạt (${ptsPct}% điểm)` : `✕ Chưa đạt (${ptsPct}% điểm)`}
            </span>
          </div>
          <div style="font-weight:700; font-size:13.5px; margin-bottom:8px; white-space:pre-line;">${escapeHtml(d.question_text)}</div>
          <div style="font-size:12.5px; margin-bottom:6px;">
            <strong>Bài làm đã nộp:</strong> <code>${escapeHtml(d.user_choice || "(Bỏ trống)")}</code>
            &nbsp;•&nbsp;
            <strong>Đáp án chuẩn:</strong> <strong style="color:var(--emerald);">${escapeHtml(d.correct_answer)}</strong>
          </div>
          <div class="q-exp" style="margin-top:6px;">
            <strong>Nhận xét & Giải thích:</strong> ${escapeHtml(d.explanation)}
          </div>
        </div>
      `;
    })
    .join("");

  document.getElementById("attemptDetailModal").classList.add("show");
}

function closeAttemptDetailModal() {
  document.getElementById("attemptDetailModal").classList.remove("show");
}

function renderLossConvergenceChart(logs) {
  const box = document.getElementById("lossChartBox");
  if (!box) return;
  if (!logs || !logs.length) {
    box.innerHTML = `<div style="text-align:center; padding:20px; color:var(--text-muted);">Chưa có nhật ký hội tụ.</div>`;
    return;
  }

  const width = 560;
  const height = 185;
  const padL = 42;
  const padR = 20;
  const padT = 22;
  const padB = 30;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const allVals = [];
  logs.forEach((r) => {
    allVals.push(parseFloat(r.training_loss));
    allVals.push(parseFloat(r.validation_loss));
  });
  const maxLoss = Math.max(...allVals, 2.2);
  const minLoss = Math.min(...allVals, 0.5);

  const getX = (i) => padL + (logs.length > 1 ? (i / (logs.length - 1)) * plotW : plotW / 2);
  const getY = (val) => padT + ((maxLoss - val) / Math.max(0.1, maxLoss - minLoss)) * plotH;

  const trainPoints = logs.map((r, i) => `${getX(i).toFixed(1)},${getY(parseFloat(r.training_loss)).toFixed(1)}`).join(" ");
  const valPoints = logs.map((r, i) => `${getX(i).toFixed(1)},${getY(parseFloat(r.validation_loss)).toFixed(1)}`).join(" ");

  const circlesTrain = logs
    .map((r, i) => `<circle cx="${getX(i).toFixed(1)}" cy="${getY(parseFloat(r.training_loss)).toFixed(1)}" r="3.5" fill="#6366F1"/>`)
    .join("");
  const circlesVal = logs
    .map((r, i) => `<circle cx="${getX(i).toFixed(1)}" cy="${getY(parseFloat(r.validation_loss)).toFixed(1)}" r="3.5" fill="#10B981"/>`)
    .join("");

  const xLabels = logs
    .map(
      (r, i) =>
        `<text x="${getX(i).toFixed(1)}" y="${height - 8}" font-size="10" text-anchor="middle" fill="#64748b">S${r.step}</text>`
    )
    .join("");

  box.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; font-size:12px; font-weight:700;">
      <span>Đường cong hội tụ QLoRA 4-bit (Cross-Entropy Loss)</span>
      <div style="display:flex; gap:14px;">
        <span style="color:#6366F1;">● Training Loss</span>
        <span style="color:#10B981;">● Validation Loss</span>
      </div>
    </div>
    <svg viewBox="0 0 ${width} ${height}" style="width:100%; height:auto; display:block;">
      <line x1="${padL}" y1="${padT}" x2="${width - padR}" y2="${padT}" stroke="#e2e8f0" stroke-dasharray="3,3"/>
      <line x1="${padL}" y1="${padT + plotH / 2}" x2="${width - padR}" y2="${padT + plotH / 2}" stroke="#e2e8f0" stroke-dasharray="3,3"/>
      <line x1="${padL}" y1="${padT + plotH}" x2="${width - padR}" y2="${padT + plotH}" stroke="#cbd5e1"/>
      <text x="${padL - 6}" y="${padT + 4}" font-size="10" text-anchor="end" fill="#64748b">${maxLoss.toFixed(2)}</text>
      <text x="${padL - 6}" y="${padT + plotH / 2 + 4}" font-size="10" text-anchor="end" fill="#64748b">${((maxLoss + minLoss) / 2).toFixed(2)}</text>
      <text x="${padL - 6}" y="${padT + plotH + 4}" font-size="10" text-anchor="end" fill="#64748b">${minLoss.toFixed(2)}</text>
      <polyline fill="none" stroke="#6366F1" stroke-width="2.5" points="${trainPoints}"/>
      <polyline fill="none" stroke="#10B981" stroke-width="2.5" stroke-dasharray="5,3" points="${valPoints}"/>
      ${circlesTrain}
      ${circlesVal}
      ${xLabels}
    </svg>
  `;
}

function renderDistBars(entries, total, colorHex = "#6366F1", labelMapper = null) {
  const safeTotal = Math.max(1, total);
  return `
    <div class="dist-bar-grid">
      ${entries
        .map(([k, v]) => {
          const pct = Math.round((v / safeTotal) * 100);
          const lbl = labelMapper ? labelMapper(k) : escapeHtml(k);
          return `
            <div class="dist-bar-item">
              <div class="dist-bar-top">
                <span>${lbl}</span>
                <span><strong>${v}</strong> (${pct}%)</span>
              </div>
              <div class="dist-bar-track">
                <div class="dist-bar-fill" style="width:${pct}%; background:${colorHex};"></div>
              </div>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

async function loadTrainingPipelineInfo() {
  const res = await apiFetch("/api/training/info");
  const data = await res.json();
  const cs = data.corpus_stats;
  const tlog = data.training_log || {};
  const total = cs.total_samples || 3600;

  document.getElementById("trainSampleTotal").innerText = total;

  const srcStatsEl = document.getElementById("trainSourceStats");
  if (srcStatsEl) {
    srcStatsEl.innerHTML = renderDistBars(Object.entries(cs.source_distribution || {}), total, "#2563eb");
  }

  const typeStatsEl = document.getElementById("trainTypeStats");
  if (typeStatsEl) {
    typeStatsEl.innerHTML = renderDistBars(
      Object.entries(cs.question_type_distribution || {}),
      total,
      "#059669",
      (k) => getQuestionTypeMeta(k).label
    );
  }

  const diffStatsEl = document.getElementById("trainDiffStats");
  if (diffStatsEl) {
    diffStatsEl.innerHTML = renderDistBars(Object.entries(cs.difficulty_distribution || {}), total, "#6d28d9");
  }

  const subjStatsEl = document.getElementById("trainSubjectStats");
  if (subjStatsEl) {
    subjStatsEl.innerHTML = Object.entries(cs.subject_distribution || {})
      .map(([k, v]) => `<span class="badge badge-slate">${escapeHtml(k)}: <strong>${v}</strong></span>`)
      .join("");
  }

  if (!explorerSelectedId) {
    document.getElementById("chatmlPreviewBox").innerText = cs.sample_chatml_preview || "";
  }

  renderLossConvergenceChart(tlog.logs || []);

  const logBody = document.getElementById("trainingLogsTableBody");
  if (logBody) {
    logBody.innerHTML = (tlog.logs || [])
      .map(
        (row) => `
      <tr>
        <td><strong>Step ${row.step}</strong></td>
        <td>${row.epoch}</td>
        <td><strong style="color:var(--primary);">${row.training_loss}</strong></td>
        <td><strong style="color:var(--emerald);">${row.validation_loss}</strong></td>
        <td><code>${row.learning_rate}</code></td>
      </tr>
    `
      )
      .join("");
  }
}

/* =========================================================================
   7. TRÌNH DUYỆT KHO DỮ LIỆU 3.600 MẪU HUGGING FACE & CHATML INSPECTOR
========================================================================= */
function debounceExplorerSearch() {
  clearTimeout(explorerSearchTimer);
  explorerSearchTimer = setTimeout(() => {
    loadDatasetExplorer(1);
  }, 260);
}

function changeExplorerPage(delta) {
  const next = explorerCurrentPage + delta;
  if (next < 1 || next > explorerTotalPages) return;
  loadDatasetExplorer(next);
}

async function loadDatasetExplorer(page = 1) {
  const source = document.getElementById("explorerSource") ? document.getElementById("explorerSource").value : "";
  const qtype = document.getElementById("explorerType") ? document.getElementById("explorerType").value : "";
  const diff = document.getElementById("explorerDiff") ? document.getElementById("explorerDiff").value : "";
  const search = document.getElementById("explorerSearch") ? document.getElementById("explorerSearch").value.trim() : "";

  const params = new URLSearchParams({
    page: String(page),
    page_size: "8",
    source,
    qtype,
    difficulty: diff,
    search,
  });

  const res = await apiFetch(`/api/training/samples?${params.toString()}`);
  const data = await res.json();

  explorerCurrentPage = data.page || 1;
  explorerTotalPages = data.total_pages || 1;
  explorerCurrentItems = data.items || [];

  const infoEl = document.getElementById("explorerPaginationInfo");
  if (infoEl) {
    infoEl.innerText = `${explorerCurrentItems.length}/${data.total} mẫu (Trang ${explorerCurrentPage}/${explorerTotalPages})`;
  }

  const prevBtn = document.getElementById("btnExplorerPrev");
  const nextBtn = document.getElementById("btnExplorerNext");
  if (prevBtn) prevBtn.disabled = explorerCurrentPage <= 1;
  if (nextBtn) nextBtn.disabled = explorerCurrentPage >= explorerTotalPages;

  const tbody = document.getElementById("explorerTableBody");
  if (!tbody) return;

  if (!explorerCurrentItems.length) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:28px; color:var(--text-muted);">Không tìm thấy mẫu huấn luyện nào khớp bộ lọc.</td></tr>`;
    return;
  }

  // Nếu chưa chọn mẫu nào hoặc mẫu đang chọn không nằm trong danh sách mới, tự động chọn mẫu đầu tiên
  if (!explorerSelectedId || !explorerCurrentItems.some((x) => x.id === explorerSelectedId)) {
    explorerSelectedId = explorerCurrentItems[0].id;
    updateChatMLInspectorView(explorerCurrentItems[0]);
  }

  tbody.innerHTML = explorerCurrentItems
    .map((item, idx) => {
      const qObj = item.output_question || {};
      const tm = getQuestionTypeMeta(item.question_type);
      const isSelected = explorerSelectedId === item.id;
      return `
        <tr class="sample-row-clickable ${isSelected ? "sample-row-active" : ""}" onclick="selectSampleForChatML(${idx})">
          <td><code>${escapeHtml(item.id)}</code></td>
          <td>
            <div style="margin-bottom:3px;"><span class="badge badge-slate">${escapeHtml(item.source || "Giáo trình")}</span></div>
            <div style="font-size:11.5px; color:var(--text-muted);">${escapeHtml(item.subject)}</div>
          </td>
          <td>
            <div style="margin-bottom:3px;"><span class="badge ${tm.cls}">${tm.label}</span></div>
            <div><span class="badge ${getBloomBadge(item.difficulty)}">${escapeHtml(item.difficulty)}</span></div>
          </td>
          <td>
            <div style="font-weight:700; color:var(--text-dark); margin-bottom:3px;">${escapeHtml(qObj.question || "")}</div>
            <div style="font-size:11.5px; color:var(--text-muted);">Ngữ cảnh: ${escapeHtml((item.input_context || "").slice(0, 110))}...</div>
          </td>
        </tr>
      `;
    })
    .join("");
}

function updateChatMLInspectorView(item) {
  if (!item) return;
  const previewBox = document.getElementById("chatmlPreviewBox");
  const metaEl = document.getElementById("chatmlSampleMeta");
  if (previewBox) {
    previewBox.innerText = item.chatml_prompt || JSON.stringify(item, null, 2);
  }
  if (metaEl) {
    metaEl.innerHTML = `Mẫu <code>${escapeHtml(item.id)}</code> • Nguồn: <strong>${escapeHtml(item.source || "Giáo trình")}</strong> • Môn: <strong>${escapeHtml(item.subject)}</strong>`;
  }
}

function selectSampleForChatML(idx) {
  const item = explorerCurrentItems[idx];
  if (!item) return;
  explorerSelectedId = item.id;
  updateChatMLInspectorView(item);

  const tbody = document.getElementById("explorerTableBody");
  if (tbody) {
    tbody.querySelectorAll("tr").forEach((tr, i) => {
      tr.classList.toggle("sample-row-active", i === idx);
    });
  }
}

async function triggerModelTraining() {
  const btn = document.getElementById("btnTriggerTraining");
  btn.disabled = true;
  btn.innerHTML = `<span>Đang huấn luyện QLoRA...</span>`;
  try {
    const res = await apiFetch("/api/training/run", {
      method: "POST",
      body: { epochs: 3, lora_rank: 16 },
    });
    const result = await res.json();
    if (res.ok) {
      await loadTrainingPipelineInfo();
      showToast(`Đã huấn luyện xong trên ${result.trained_samples} mẫu! Final Loss: ${result.final_training_loss}`);
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = `
      <svg class="svg-icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
      <span>Chạy Huấn Luyện Lại QLoRA</span>
    `;
  }
}

/* =========================================================================
   KHỞI ĐỘNG ỨNG DỤNG KHI MỞ TRANG WEB
========================================================================= */
window.addEventListener("DOMContentLoaded", async () => {
  const savedTheme = localStorage.getItem("aiexam_theme");
  applyThemeState(savedTheme === "dark");

  if (authToken) {
    try {
      const res = await fetch("/api/auth/me", {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        onAuthSuccess(authToken, data.user);
        return;
      }
    } catch (e) {}
  }
  clearSessionAndShowAuth();
});
