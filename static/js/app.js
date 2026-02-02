/**
 * YouTube Karaoke Web App - JavaScript
 */

// Global state
let pollInterval = null;
let currentVideoFile = 'final_video.mp4';

// Default settings (should match web_app_flask.py Settings class)
const DEFAULT_YOUTUBE_URL = "https://www.youtube.com/watch?v=6E_161JvL2Q";
const DEFAULT_START_TIME = "00:01:30";
const DEFAULT_END_TIME = "00:02:30";

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('YouTube Web App initialized');
    
    // Load initial data
    refreshAll();
    
    // Start polling for status updates
    startPolling();
    
    // Set up tab change handlers
    setupTabHandlers();
});

// ================= Polling =================

function startPolling() {
    // Poll every 2 seconds for status updates
    pollInterval = setInterval(updateStatus, 2000);
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

async function updateStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        // Update step statuses
        if (data.step_status) {
            data.step_status.forEach((status, index) => {
                updateStepStatus(index, status);
            });
        }
        
        // Update logs
        if (data.logs && data.logs.length > 0) {
            updateLogArea(data.logs);
        }
        
        // Update files info
        if (data.files) {
            updateFilesList(data.files);
        }
    } catch (error) {
        console.error('Error updating status:', error);
    }
}

// ================= Step Status =================

function updateStepStatus(stepNum, status) {
    const statusEl = document.getElementById(`status-${stepNum}`);
    if (statusEl) {
        statusEl.textContent = status || '○';
        
        // Update status class
        statusEl.className = 'step-status';
        if (status === '✓') {
            statusEl.classList.add('status-success');
        } else if (status === '✗') {
            statusEl.classList.add('status-error');
        } else if (status === '⏳') {
            statusEl.classList.add('status-processing');
        } else {
            statusEl.classList.add('status-pending');
        }
    }
}

// ================= Step Execution =================

async function runStep(stepNum) {
    // Get current settings from UI, use defaults if empty
    const urlInput = document.getElementById('youtube-url');
    const startTimeInput = document.getElementById('start-time');
    const endTimeInput = document.getElementById('end-time');
    
    const url = urlInput?.value?.trim() || DEFAULT_YOUTUBE_URL;
    const startTime = startTimeInput?.value?.trim() || DEFAULT_START_TIME;
    const endTime = endTimeInput?.value?.trim() || DEFAULT_END_TIME;
    
    // Debug: log the values being sent
    console.log(`Running step ${stepNum}: URL=${url}, start=${startTime}, end=${endTime}`);
    
    // Validate times for cut step (step 1)
    if (stepNum === 1) {
        if (!validateTimes(startTime, endTime)) {
            showToast('خطأ', 'وقت النهاية يجب أن يكون بعد وقت البداية');
            return;
        }
    }
    
    // Update status to processing
    updateStepStatus(stepNum, '⏳');
    
    // Show processing modal
    showProcessingModal();
    
    try {
        const response = await fetch(`/api/step/${stepNum}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url: url,
                start_time: startTime,
                end_time: endTime
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            showToast('خطأ', data.error);
            updateStepStatus(stepNum, '✗');
            hideProcessingModal();
            return;
        } else {
            showToast('نجاح', data.message);
        }
    } catch (error) {
        console.error('Error running step:', error);
        showToast('خطأ', 'حدث خطأ في الاتصال');
        updateStepStatus(stepNum, '✗');
        hideProcessingModal();
        return;
    }
    
    // Poll until processing is complete
    await waitForProcessingComplete();
}

async function waitForProcessingComplete() {
    const maxWaitTime = 300000; // 5 minutes max
    const pollInterval = 1000; // 1 second
    let waited = 0;
    
    while (waited < maxWaitTime) {
        await new Promise(resolve => setTimeout(resolve, pollInterval));
        waited += pollInterval;
        
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            
            // Update all step statuses
            if (data.step_status) {
                data.step_status.forEach((status, index) => {
                    updateStepStatus(index, status);
                });
            }
            
            // Check if processing is complete
            if (!data.is_processing) {
                hideProcessingModal();
                return;
            }
        } catch (error) {
            console.error('Error polling status:', error);
        }
    }
    
    // Timeout - hide modal anyway
    console.warn('Processing wait timeout');
    hideProcessingModal();
}

async function runAllSteps() {
    showToast('المعالجة', 'سيتم تشغيل جميع الخطوات تلقائياً...');
    
    // Run steps in order
    for (let i = 0; i < 8; i++) {
        if (i === 3 || i === 5) continue; // Skip edit steps
        await runStep(i);
        await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1 second between steps
    }
}

// ================= Tab Navigation =================

function goToTab(tabId) {
    const tabEl = document.getElementById(tabId);
    if (tabEl) {
        const tab = new bootstrap.Tab(tabEl);
        tab.show();
    }
}

function setupTabHandlers() {
    // Tab shown event - refresh data
    const triggerTabList = [].slice.call(document.querySelectorAll('#main-tabs button'));
    triggerTabList.forEach(function(triggerEl) {
        triggerEl.addEventListener('shown.bs.tab', function(event) {
            const targetTab = event.target.getAttribute('data-bs-target');
            
            if (targetTab === '#german-content') {
                reloadGerman();
            } else if (targetTab === '#arabic-content') {
                reloadArabic();
            } else if (targetTab === '#preview-content') {
                refreshFiles();
            }
        });
    });
}

// ================= File Operations =================

async function refreshAll() {
    try {
        const response = await fetch('/api/refresh');
        const data = await response.json();
        
        // Update step statuses
        if (data.step_status) {
            data.step_status.forEach((status, index) => {
                updateStepStatus(index, status);
            });
        }
        
        // Update files
        if (data.files) {
            updateFilesList(data.files);
        }
        
        console.log('Data refreshed');
    } catch (error) {
        console.error('Error refreshing:', error);
    }
}

// German SRT
async function loadGermanFromFile() {
    try {
        const response = await fetch('/api/file/german');
        const data = await response.json();
        
        const editor = document.getElementById('german-editor');
        if (editor && data.content) {
            editor.value = data.content;
            document.getElementById('german-status').textContent = 'تم التحميل';
            showToast('نجاح', 'تم تحميل الملف');
        } else {
            showToast('تنبيه', 'الملف غير موجود');
        }
    } catch (error) {
        console.error('Error loading German:', error);
        showToast('خطأ', 'فشل في تحميل الملف');
    }
}

async function saveGerman() {
    const editor = document.getElementById('german-editor');
    const content = editor ? editor.value : '';
    
    try {
        const response = await fetch('/api/file/german', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ content: content })
        });
        
        const data = await response.json();
        showToast('نجاح', data.message || 'تم الحفظ');
    } catch (error) {
        console.error('Error saving German:', error);
        showToast('خطأ', 'فشل في حفظ الملف');
    }
}

async function reloadGerman() {
    try {
        const response = await fetch('/api/file/reload/german');
        const data = await response.json();
        
        const editor = document.getElementById('german-editor');
        if (editor && data.content) {
            editor.value = data.content;
            document.getElementById('german-status').textContent = 'تم إعادة التحميل';
        }
    } catch (error) {
        console.error('Error reloading German:', error);
    }
}

// Arabic SRT
async function loadArabicFromFile() {
    try {
        const response = await fetch('/api/file/arabic');
        const data = await response.json();
        
        const editor = document.getElementById('arabic-editor');
        if (editor && data.content) {
            editor.value = data.content;
            document.getElementById('arabic-status').textContent = 'تم التحميل';
            showToast('نجاح', 'تم تحميل الملف');
        } else {
            showToast('تنبيه', 'الملف غير موجود');
        }
    } catch (error) {
        console.error('Error loading Arabic:', error);
        showToast('خطأ', 'فشل في تحميل الملف');
    }
}

async function saveArabic() {
    const editor = document.getElementById('arabic-editor');
    const content = editor ? editor.value : '';
    
    try {
        const response = await fetch('/api/file/arabic', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ content: content })
        });
        
        const data = await response.json();
        showToast('نجاح', data.message || 'تم الحفظ');
    } catch (error) {
        console.error('Error saving Arabic:', error);
        showToast('خطأ', 'فشل في حفظ الملف');
    }
}

async function reloadArabic() {
    try {
        const response = await fetch('/api/file/reload/arabic');
        const data = await response.json();
        
        const editor = document.getElementById('arabic-editor');
        if (editor && data.content) {
            editor.value = data.content;
            document.getElementById('arabic-status').textContent = 'تم إعادة التحميل';
        }
    } catch (error) {
        console.error('Error reloading Arabic:', error);
    }
}

// Load functions for quick access
function loadGerman() {
    goToTab('german-tab');
    loadGermanFromFile();
}

function loadArabic() {
    goToTab('arabic-tab');
    loadArabicFromFile();
}

// Proceed functions
async function proceedFromGerman() {
    await saveGerman();
    goToTab('process-tab');
    
    // Continue with translation
    await runStep(4); // Translate
    await runStep(6); // Create ASS
    await runStep(7); // Produce Video
}

async function proceedToVideo() {
    await saveArabic();
    goToTab('process-tab');
    
    // Create ASS and produce video
    await runStep(6);
    await runStep(7);
}

// ================= Files Info =================

async function refreshFiles() {
    try {
        const response = await fetch('/api/file/files_info');
        const data = await response.json();
        updateFilesList(data);
    } catch (error) {
        console.error('Error refreshing files:', error);
    }
}

function updateFilesList(files) {
    const listEl = document.getElementById('files-list');
    if (!listEl) return;
    
    if (!files || files.length === 0) {
        listEl.innerHTML = '<li class="list-group-item text-muted">لا توجد ملفات</li>';
        return;
    }
    
    let html = '';
    files.forEach(file => {
        const icon = file.exists ? '✓' : '○';
        const statusClass = file.exists ? 'exists' : 'not-exists';
        html += `
            <li class="list-group-item ${statusClass}">
                <i class="bi bi-${file.exists ? 'check-circle' : 'circle'}"></i>
                ${file.name}: ${file.file} (${file.size})
            </li>
        `;
    });
    listEl.innerHTML = html;
    
    // Update video preview if exists
    const finalVideo = files.find(f => f.name === 'Final Video');
    if (finalVideo && finalVideo.exists) {
        updateVideoPreview();
    }
}

// ================= Log Area =================

function updateLogArea(logs) {
    const logArea = document.getElementById('log-area');
    if (!logArea) return;
    
    const logText = logs.join('\n');
    logArea.textContent = logText;
    logArea.scrollTop = logArea.scrollHeight;
}

function clearLogs() {
    const logArea = document.getElementById('log-area');
    if (logArea) {
        logArea.textContent = 'السجل محذوف\n';
    }
}

// ================= Video Preview =================

function updateVideoPreview() {
    const previewEl = document.getElementById('video-preview');
    const previewText = document.getElementById('video-preview-text');
    
    if (previewText) {
        previewText.innerHTML = `
            <video controls style="max-width: 100%; max-height: 400px;">
                <source src="/${currentVideoFile}" type="video/mp4">
                متصفحك لا يدعم الفيديو
            </video>
        `;
    }
}

function playVideo() {
    // Open video in new window/tab
    window.open(`/${currentVideoFile}`, '_blank');
}

function downloadVideo() {
    // Create a link to download the video file
    const link = document.createElement('a');
    link.href = `/${currentVideoFile}`;
    link.download = currentVideoFile;
    link.target = '_blank';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showToast('تحميل', 'جاري تحميل الفيديو...');
}

function selectVideo() {
    const input = document.getElementById('video-file-input');
    if (input) {
        input.click();
    }
}

function handleVideoSelect(event) {
    const file = event.target.files[0];
    if (file) {
        currentVideoFile = file.name;
        showToast('نجاح', `تم اختيار: ${file.name}`);
    }
}

function openFolder() {
    // This would typically open the folder containing the video
    // On web, we can't directly open folders, so we show a message
    showToast('معلومات', 'المجلد: /Users/emadelddinjuha/Desktop/youtube_karaoke');
}

// ================= File Management =================

async function clearFiles() {
    if (!confirm('هل أنت متأكد من حذف جميع الملفات المُنشأة؟')) {
        return;
    }
    
    try {
        const response = await fetch('/api/clear', { method: 'POST' });
        const data = await response.json();
        
        showToast('نجاح', data.message);
        refreshAll();
        
        // Reset all status indicators
        for (let i = 0; i < 8; i++) {
            updateStepStatus(i, '○');
        }
    } catch (error) {
        console.error('Error clearing files:', error);
        showToast('خطأ', 'فشل في حذف الملفات');
    }
}

// ================= Modal & Toast =================

function showProcessingModal() {
    const modalEl = document.getElementById('processing-modal');
    if (modalEl) {
        const modal = new bootstrap.Modal(modalEl);
        modal.show();
    }
}

function hideProcessingModal() {
    const modalEl = document.getElementById('processing-modal');
    if (modalEl) {
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) {
            modal.hide();
        }
    }
}

function showToast(title, message) {
    const toastEl = document.getElementById('live-toast');
    const toastTitle = document.getElementById('toast-title');
    const toastMessage = document.getElementById('toast-message');
    
    if (toastTitle && toastMessage && toastEl) {
        toastTitle.textContent = title;
        toastMessage.textContent = message;
        
        const toast = new bootstrap.Toast(toastEl, {
            autohide: true,
            delay: 3000
        });
        toast.show();
    }
}

// ================= Utility Functions =================

/**
 * Validate that end time is after start time
 * @param {string} startTime - Start time in HH:MM:SS or MM:SS format
 * @param {string} endTime - End time in HH:MM:SS or MM:SS format
 * @returns {boolean} - True if valid, false otherwise
 */
function validateTimes(startTime, endTime) {
    try {
        // Parse start time
        let startSeconds;
        if (startTime.includes(':')) {
            const startParts = startTime.split(':');
            if (startParts.length === 3) {
                startSeconds = parseInt(startParts[0]) * 3600 + parseInt(startParts[1]) * 60 + parseInt(startParts[2]);
            } else if (startParts.length === 2) {
                startSeconds = parseInt(startParts[0]) * 60 + parseInt(startParts[1]);
            } else {
                return false;
            }
        } else {
            startSeconds = parseInt(startTime);
        }
        
        // Parse end time
        let endSeconds;
        if (endTime.includes(':')) {
            const endParts = endTime.split(':');
            if (endParts.length === 3) {
                endSeconds = parseInt(endParts[0]) * 3600 + parseInt(endParts[1]) * 60 + parseInt(endParts[2]);
            } else if (endParts.length === 2) {
                endSeconds = parseInt(endParts[0]) * 60 + parseInt(endParts[1]);
            } else {
                return false;
            }
        } else {
            endSeconds = parseInt(endTime);
        }
        
        // Check if end is after start
        return endSeconds > startSeconds;
    } catch (e) {
        console.error('Error validating times:', e);
        return false;
    }
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Export for potential use
window.YouTubeKaraoke = {
    runStep,
    runAllSteps,
    goToTab,
    saveGerman,
    saveArabic,
    loadGerman,
    loadArabic,
    refreshAll,
    clearFiles,
    showToast,
    playVideo,
    downloadVideo
};

