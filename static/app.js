const $ = (id) => document.getElementById(id);

const media = { images: [], videos: [], audios: [] };

// المسارات نسبية لأن الواجهة والخادم على نفس النطاق
function headers(extra = {}) {
  return { "X-API-Key": $("apiKey").value.trim(), ...extra };
}

// حفظ مفتاح API محليًا لتسهيل الاستخدام
const savedKey = localStorage.getItem("apiKey");
if (savedKey) $("apiKey").value = savedKey;
$("apiKey").addEventListener("change", () =>
  localStorage.setItem("apiKey", $("apiKey").value)
);

$("uploadBtn").addEventListener("click", async () => {
  const fileInput = $("mediaFile");
  if (!fileInput.files.length) {
    alert("اختر ملفًا أولاً.");
    return;
  }
  if (!$("apiKey").value) {
    alert("أدخل مفتاح API.");
    return;
  }
  const file = fileInput.files[0];
  const form = new FormData();
  form.append("file", file);

  $("uploadBtn").disabled = true;
  $("uploadBtn").textContent = "جاري الرفع...";
  try {
    const res = await fetch("/api/upload", {
      method: "POST",
      headers: headers(),
      body: form,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "فشل الرفع");

    const type = file.type.startsWith("video") ? "videos" : "images";
    media[type].push(data.url);
    const li = document.createElement("li");
    li.textContent = `${type === "videos" ? "🎥" : "🖼️"} ${data.url}`;
    $("mediaList").appendChild(li);
    fileInput.value = "";
  } catch (e) {
    alert("خطأ: " + e.message);
  } finally {
    $("uploadBtn").disabled = false;
    $("uploadBtn").textContent = "رفع الملف";
  }
});

$("generateBtn").addEventListener("click", async () => {
  if (!$("apiKey").value) {
    alert("أدخل مفتاح API.");
    return;
  }
  const payload = {
    type: $("mode").value,
    prompt: $("prompt").value.trim(),
    images: media.images,
    videos: media.videos,
    audios: media.audios,
    resolution: $("resolution").value,
    aspect_ratio: $("aspect").value,
    duration: parseInt($("duration").value, 10),
  };

  $("generateBtn").disabled = true;
  $("statusCard").classList.remove("hidden");
  $("spinner").classList.remove("hidden");
  $("resultVideo").classList.add("hidden");
  $("downloadLink").classList.add("hidden");
  $("statusText").textContent = "جاري بدء المهمة...";

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: headers({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "فشل بدء التوليد");
    pollStatus(data.taskId);
  } catch (e) {
    finishError(e.message);
  }
});

async function pollStatus(taskId) {
  try {
    const res = await fetch(`/api/status/${taskId}`, {
      headers: headers(),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "خطأ في الاستعلام");

    $("statusText").textContent = data.message || data.status;

    if (data.status === "done") {
      $("spinner").classList.add("hidden");
      const video = $("resultVideo");
      video.src = data.videoUrl;
      video.classList.remove("hidden");
      const link = $("downloadLink");
      link.href = data.videoUrl;
      link.classList.remove("hidden");
      $("generateBtn").disabled = false;
    } else if (data.status === "error") {
      finishError(data.message);
    } else {
      setTimeout(() => pollStatus(taskId), 4000);
    }
  } catch (e) {
    finishError(e.message);
  }
}

function finishError(msg) {
  $("spinner").classList.add("hidden");
  $("statusText").textContent = "❌ " + msg;
  $("generateBtn").disabled = false;
}