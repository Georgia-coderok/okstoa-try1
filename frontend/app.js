// ============================================================================
// 1. REAL AGENT ADAPTER (Connected to Backend API via Fetch Stream)
// ============================================================================
const API_BASE_URL = "http://localhost:8000"; // Replace with your Python backend URL

async function* streamAgentEvents(prompt, project, attachment) {
  yield { type: "status", message: "Connecting to agent..." };

  try {
    const response = await fetch(`${API_BASE_URL}/api/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
      },
      body: JSON.stringify({ prompt, project, attachment })
    });

    if (!response.ok) {
      throw new Error(`Server error: ${response.statusText}`);
    }

    // Read the incoming stream chunk by chunk
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // Retain incomplete line in buffer

      for (const line of lines) {
        if (!line.trim()) continue;
        if (line.startsWith("data: ")) {
          const eventData = JSON.parse(line.substring(6));
          yield eventData;
        }
      }
    }
  } catch (err) {
    yield { type: "status", message: "Connection Error: " + err.message };
    throw err;
  }
}

async function* resumeAgentApproval(actionId, approved) {
  yield { type: "status", message: approved ? "Sending approval to agent..." : "Canceling action..." };

  try {
    const response = await fetch(`${API_BASE_URL}/api/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actionId, approved })
    });

    if (!response.ok) throw new Error("Failed to process approval");

    const data = await response.json();
    yield {
      type: "text_delta",
      content: data.message || (approved ? "\n\nApproved: Action executed." : "\n\nRejected: Operation aborted.")
    };
    yield { type: "done" };
  } catch (err) {
    yield { type: "status", message: "Error: " + err.message };
  }
}

// ============================================================================
// 2. MULTI-FORMAT IMAGE ATTACHMENT HANDLERS
// ============================================================================
const EXTRA_IMAGE_EXTS = /\.(heic|heif|tif|tiff|avif|webp|svg|bmp|ico|png|jpe?g|gif)$/i;

const chatFeed = document.getElementById("chat-feed");
const promptForm = document.getElementById("prompt-form");
const promptInput = document.getElementById("prompt-input");
const sendBtn = document.getElementById("send-btn");
const activeProjectTitle = document.getElementById("active-project-title");
const sessionItems = document.querySelectorAll(".session-item");
const presetChips = document.querySelectorAll(".preset-chip");
const newSessionBtn = document.getElementById("new-session-btn");
const workspaceEl = document.getElementById("workspace");

const attachBtn = document.getElementById("attach-btn");
const imageFileInput = document.getElementById("image-file-input");
const previewBar = document.getElementById("attachment-preview-bar");
const previewThumb = document.getElementById("preview-thumb");
const previewFilename = document.getElementById("preview-filename");
const removeAttachmentBtn = document.getElementById("remove-attachment-btn");

let stagedImage = null;
let currentProject = "Default Project";

function isSupportedImageFile(file) {
  if (!file) return false;
  return file.type.startsWith("image/") || EXTRA_IMAGE_EXTS.test(file.name);
}

function getFallbackMimeType(file) {
  if (file.type) return file.type;
  const ext = file.name.split(".").pop()?.toLowerCase();
  const map = {
    heic: "image/heic",
    heif: "image/heif",
    tif: "image/tiff",
    tiff: "image/tiff",
    avif: "image/avif",
    svg: "image/svg+xml",
    webp: "image/webp",
    bmp: "image/bmp",
    ico: "image/x-icon",
  };
  return map[ext] || "application/octet-stream";
}

function stageImageFile(file) {
  if (!isSupportedImageFile(file)) return;

  const mimeType = getFallbackMimeType(file);
  const reader = new FileReader();

  reader.onload = () => {
    const dataUrl = reader.result;
    const base64Data = dataUrl.split(",")[1];
    const canPreviewNatively = /^image\/(png|jpeg|jpg|gif|webp|svg\+xml|avif|bmp|x-icon)$/i.test(mimeType);

    stagedImage = {
      name: file.name || `pasted_plan_${Date.now()}.png`,
      mimeType,
      base64Data,
      dataUrl: canPreviewNatively ? dataUrl : null,
    };

    if (canPreviewNatively) {
      previewThumb.src = dataUrl;
      previewThumb.style.display = "block";
    } else {
      previewThumb.removeAttribute("src");
      previewThumb.style.display = "none";
    }

    previewFilename.textContent = `${stagedImage.name} (${mimeType})`;
    previewBar.classList.remove("hidden");
    promptInput.focus();
  };

  reader.readAsDataURL(file);
}

function clearStagedImage() {
  stagedImage = null;
  imageFileInput.value = "";
  previewThumb.removeAttribute("src");
  previewThumb.style.display = "block";
  previewBar.classList.add("hidden");
}

if (attachBtn && imageFileInput) {
  attachBtn.addEventListener("click", () => imageFileInput.click());
  imageFileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      stageImageFile(e.target.files[0]);
    }
  });
}

if (promptInput) {
  promptInput.addEventListener("paste", (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        e.preventDefault();
        stageImageFile(item.getAsFile());
        break;
      }
    }
  });
}

if (workspaceEl) {
  workspaceEl.addEventListener("dragover", (e) => {
    e.preventDefault();
    workspaceEl.classList.add("drag-active");
  });
  workspaceEl.addEventListener("dragleave", () => {
    workspaceEl.classList.remove("drag-active");
  });
  workspaceEl.addEventListener("drop", (e) => {
    e.preventDefault();
    workspaceEl.classList.remove("drag-active");
    if (e.dataTransfer?.files?.[0]) {
      stageImageFile(e.dataTransfer.files[0]);
    }
  });
}

if (removeAttachmentBtn) {
  removeAttachmentBtn.addEventListener("click", clearStagedImage);
}

// ============================================================================
// 3. STUDIO UI CONTROLLER
// ============================================================================
function appendUserMessage(text, imageAttachment) {
  const wrapper = document.createElement("div");
  wrapper.className = "message user";

  const meta = document.createElement("div");
  meta.className = "msg-meta";
  meta.textContent = imageAttachment ? "ARCHITECT // PLAN + DIRECTIVE" : "ARCHITECT // DIRECTIVE";

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  if (imageAttachment) {
    const frame = document.createElement("div");
    frame.className = "msg-image-frame";

    if (imageAttachment.dataUrl) {
      const img = document.createElement("img");
      img.src = imageAttachment.dataUrl;
      img.alt = imageAttachment.name;
      frame.appendChild(img);
    }

    const caption = document.createElement("div");
    caption.className = "msg-image-caption";
    caption.textContent = `FILE: ${imageAttachment.name} [${imageAttachment.mimeType}]`;
    frame.appendChild(caption);

    bubble.appendChild(frame);
  }

  const textNode = document.createElement("div");
  textNode.textContent = text;
  bubble.appendChild(textNode);

  wrapper.appendChild(meta);
  wrapper.appendChild(bubble);
  chatFeed.appendChild(wrapper);
  chatFeed.scrollTop = chatFeed.scrollHeight;
}

function createAssistantMessageContainer() {
  const wrapper = document.createElement("div");
  wrapper.className = "message assistant";

  const meta = document.createElement("div");
  meta.className = "msg-meta";
  meta.textContent = "STOA INTELLIGENCE";

  const statusEl = document.createElement("div");
  statusEl.className = "status-pill";

  const bubbleEl = document.createElement("div");
  bubbleEl.className = "bubble";

  wrapper.appendChild(meta);
  wrapper.appendChild(statusEl);
  wrapper.appendChild(bubbleEl);
  chatFeed.appendChild(wrapper);

  return { wrapper, statusEl, bubbleEl };
}

function renderApprovalCard(container, event, bubbleEl, statusEl) {
  const card = document.createElement("div");
  card.className = "approval-card";

  card.innerHTML = `
    <div class="approval-header">TRANSMITTAL SIGN-OFF // ${event.actionId}</div>
    <p>${event.summary}</p>
    <pre>${event.payload}</pre>
    <div class="approval-actions">
      <button type="button" class="btn-approve">APPROVE &amp; ISSUE</button>
      <button type="button" class="btn-reject">HOLD REVISION</button>
    </div>
  `;

  const approveBtn = card.querySelector(".btn-approve");
  const rejectBtn = card.querySelector(".btn-reject");

  const handleDecision = async (approved) => {
    approveBtn.disabled = true;
    rejectBtn.disabled = true;
    await consumeEventStream(resumeAgentApproval(event.actionId, approved), {
      wrapper: container,
      statusEl,
      bubbleEl,
    });
  };

  approveBtn.addEventListener("click", () => handleDecision(true));
  rejectBtn.addEventListener("click", () => handleDecision(false));

  container.appendChild(card);
  chatFeed.scrollTop = chatFeed.scrollHeight;
}

async function consumeEventStream(eventStream, uiTargets) {
  const { wrapper, statusEl, bubbleEl } = uiTargets;
  sendBtn.disabled = true;

  try {
    for await (const event of eventStream) {
      if (event.type === "status") {
        statusEl.textContent = "▸ " + event.message;
      } else if (event.type === "text_delta") {
        bubbleEl.textContent += event.content;
      } else if (event.type === "approval_required") {
        renderApprovalCard(wrapper, event, bubbleEl, statusEl);
      } else if (event.type === "done") {
        statusEl.textContent = "";
      }
      chatFeed.scrollTop = chatFeed.scrollHeight;
    }
  } catch (err) {
    statusEl.textContent = "SYSTEM ERROR: " + err.message;
  } finally {
    sendBtn.disabled = false;
    promptInput.focus();
  }
}

async function submitDirective(promptText) {
  const textToSend = promptText || (stagedImage ? "Analyze attached architectural drawing." : "");
  if ((!textToSend && !stagedImage) || sendBtn.disabled) return;

  const attachmentToSend = stagedImage;
  promptInput.value = "";
  clearStagedImage();

  appendUserMessage(textToSend, attachmentToSend);
  const uiTargets = createAssistantMessageContainer();
  await consumeEventStream(streamAgentEvents(textToSend, currentProject, attachmentToSend), uiTargets);
}

if (promptForm) {
  promptForm.addEventListener("submit", (e) => {
    e.preventDefault();
    submitDirective(promptInput.value.trim());
  });
}

sessionItems.forEach((item) => {
  item.addEventListener("click", () => {
    sessionItems.forEach((el) => el.classList.remove("active"));
    item.classList.add("active");
    currentProject = item.dataset.project;
    if (activeProjectTitle) activeProjectTitle.textContent = currentProject;
  });
});

presetChips.forEach((chip) => {
  chip.addEventListener("click", () => {
    submitDirective(chip.dataset.prompt);
  });
});

if (newSessionBtn && chatFeed) {
  newSessionBtn.addEventListener("click", () => {
    const messages = chatFeed.querySelectorAll(".message");
    messages.forEach((m) => m.remove());
    clearStagedImage();
  });
}