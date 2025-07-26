// script.js

// This script primarily handles client-side UI updates and AJAX calls to the Flask backend.
// All API keys and heavy lifting (Apify data retrieval, AI analysis) are handled by app.py on the server.

const SECRET_LOG_CODE = "1234"; // The secret code to reveal logs

// --- Custom Console for Logging to Session Storage (Client-side logs) ---
const logKey = 'appLogs';
const originalConsoleLog = console.log;
const originalConsoleError = console.error;

function getLogs() {
    try {
        const logs = sessionStorage.getItem(logKey);
        return logs ? JSON.parse(logs) : [];
    } catch (e) {
        originalConsoleError("Error parsing logs from session storage:", e);
        return [];
    }
}

function addLog(type, message) {
    const logs = getLogs();
    const timestamp = new Date().toISOString();
    logs.push({ type, timestamp, message: String(message) }); // Ensure message is a string
    try {
        sessionStorage.setItem(logKey, JSON.stringify(logs));
    } catch (e) {
        originalConsoleError("Error saving logs to session storage:", e);
    }
}

console.log = function(...args) {
    originalConsoleLog.apply(console, args);
    addLog('INFO', args.map(arg => typeof arg === 'object' ? JSON.stringify(arg) : arg).join(' '));
};

console.error = function(...args) {
    originalConsoleError.apply(console, args);
    addLog('ERROR', args.map(arg => typeof arg === 'object' ? JSON.stringify(arg) : arg).join(' '));
};

// --- Functions for page logic ---

// Function to handle loading screen logic on loading.html
async function handleLoadingPage() {
    console.log("Client: Loading page initiated.");
    const progressBar = document.getElementById('progressBar');
    const loadingTextElement = document.getElementById('loadingText');

    let progress = 0;
    // Set total duration to 90 seconds (1.5 minutes) for a longer feel
    const totalDuration = 90000; // 90 seconds in milliseconds
    const updateInterval = 100; // How often to update the progress bar in ms

    const messages = [
        "Connecting to data sources... This might take a moment.",
        "Retrieving profile details and recent content...",
        "Gathering associated interactions for each content piece...",
        "Processing raw data for AI analysis...",
        "Did you know consistency in posting can significantly boost engagement?",
        "Sending processed information to the AI for deep insights...",
        "AI is generating an opinion and an overall score...",
        "Consider using diverse content formats like Reels and Stories to reach a wider audience!",
        "Finalizing analysis and preparing your personalized results...",
        "Almost there! Just a few more moments...",
        "Optimizing your bio with relevant keywords can improve discoverability!",
        "Compiling the final report...",
        "Analysis complete. Redirecting..." // This message will be shown just before redirect
    ];
    let messageIndex = 0;
    let textInterval;

    // Function to update text with a fade effect
    const updateLoadingText = () => {
        if (loadingTextElement && messageIndex < messages.length -1) { // Don't update the last message until redirect
            loadingTextElement.style.opacity = '0'; // Fade out
            setTimeout(() => {
                loadingTextElement.textContent = messages[messageIndex];
                loadingTextElement.style.opacity = '1'; // Fade in
                messageIndex++;
            }, 500); // Wait for fade out before changing text and fading in
        }
    };

    // Initial text update
    updateLoadingText();
    // Set interval for changing text every ~7 seconds (adjusted for 13 messages over 90s, excluding last one)
    textInterval = setInterval(updateLoadingText, totalDuration / (messages.length - 1));


    const progressInterval = setInterval(() => {
        progress += (updateInterval / totalDuration) * 100;
        if (progressBar) {
            progressBar.style.width = `${Math.min(progress, 99)}%`; // Cap at 99% until analysis is truly done
        }
    }, updateInterval);

    try {
        console.log("Client: Making AJAX call to Flask backend to perform analysis.");
        const response = await fetch('/perform_analysis');
        const data = await response.json();

        // Ensure all intervals are cleared when the backend response is received
        clearInterval(progressInterval);
        clearInterval(textInterval);

        if (progressBar) {
            progressBar.style.width = '100%'; // Immediately jump to 100%
            progressBar.style.transition = 'width 0.3s ease-out'; // Smooth transition to 100%
        }
        if (loadingTextElement) {
            // Set the final "Redirecting..." message right before redirect
            loadingTextElement.textContent = messages[messages.length - 1];
            loadingTextElement.style.opacity = '1';
        }


        if (data.status === 'complete') {
            console.log("Client: Analysis complete. Redirecting to results page.");
            // Redirect to results page after a small delay to show 100%
            setTimeout(() => {
                window.location.href = '/results';
            }, 500);
        } else {
            console.error("Client: Analysis failed:", data.message);
            sessionStorage.setItem('errorMessage', data.message); // Store error message for display on index/results
            window.location.href = '/'; // Go back to input on error
        }
    } catch (error) {
        // Ensure all intervals are cleared on error
        clearInterval(progressInterval);
        clearInterval(textInterval);

        console.error("Client: Error during analysis fetch:", error);
        sessionStorage.setItem('errorMessage', `An error occurred during analysis: ${error.message}`);
        window.location.href = '/'; // Go back to input on error
        if (progressBar) progressBar.style.width = '0%'; // Reset progress bar on error
    }
}

// Function to draw the score wheel on results.html
function drawScoreWheel(canvas, score) {
    const ctx = canvas.getContext('2d');
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = Math.min(centerX, centerY) - 10; // Small padding

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw background circle (total score)
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
    ctx.strokeStyle = '#e0e0e0'; // Light gray
    ctx.lineWidth = 10;
    ctx.stroke();

    // Draw score arc
    const startAngle = -0.5 * Math.PI; // Start at top
    const endAngle = startAngle + (score / 10) * 2 * Math.PI; // Calculate end angle based on score
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, startAngle, endAngle);
    ctx.strokeStyle = '#8B5CF6'; // Purple (Tailwind purple-500/600 equivalent)
    ctx.lineWidth = 10;
    ctx.stroke();

    // Display score text in the center
    ctx.fillStyle = '#333'; // Dark gray text
    ctx.font = 'bold 30px Inter';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(score, centerX, centerY);
}


// Function to handle results display and log viewer on results.html
function handleResultsPage() {
    console.log("Client: Results page initiated.");

    // Populate Overall Score and draw wheel
    const overallScoreDisplay = document.getElementById('overallScoreDisplay');
    const scoreWheelCanvas = document.getElementById('scoreWheelCanvas');
    // The score is now passed directly from Flask to the Jinja2 template
    // We need to get it from the HTML element's text content
    if (overallScoreDisplay && scoreWheelCanvas) {
        const score = parseInt(overallScoreDisplay.textContent, 10);
        if (!isNaN(score)) {
            drawScoreWheel(scoreWheelCanvas, score);
        } else {
            console.error("Client: Could not parse overall score for wheel display.");
            overallScoreDisplay.textContent = "N/A";
        }
    } else {
        console.warn("Client: Score display elements not found on results page.");
    }

    // --- Log Viewer Logic ---
    const logCodeInput = document.getElementById('logCodeInput');
    const logDisplayArea = document.getElementById('logDisplayArea');

    if (logCodeInput && logDisplayArea) {
        logCodeInput.addEventListener('input', () => {
            if (logCodeInput.value === SECRET_LOG_CODE) {
                logDisplayArea.classList.remove('hidden');
                const storedLogs = getLogs();
                logDisplayArea.textContent = storedLogs.map(log =>
                    `[${log.timestamp}] [${log.type}] ${log.message}`
                ).join('\n');
                logCodeInput.value = ''; // Clear input after successful entry
            } else {
                logDisplayArea.classList.add('hidden');
            }
        });
    } else {
        console.warn("Client: Log viewer elements not found on results page.");
    }
}


// --- Initialize based on current page ---
document.addEventListener('DOMContentLoaded', () => {
    // Check if the current page is index.html
    if (window.location.pathname.endsWith('index.html') || window.location.pathname === '/') {
        // Any specific client-side setup for index.html (e.g., displaying error messages from session)
        const errorMessageElement = document.getElementById('errorMessage');
        const storedErrorMessage = sessionStorage.getItem('errorMessage');
        if (storedErrorMessage) {
            if (errorMessageElement) {
                errorMessageElement.textContent = storedErrorMessage;
                errorMessageElement.classList.remove('hidden');
            }
            sessionStorage.removeItem('errorMessage'); // Clear it after displaying
        }
    } else if (window.location.pathname.endsWith('loading.html') || window.location.pathname === '/loading') {
        handleLoadingPage();
    } else if (window.location.pathname.endsWith('results.html') || window.location.pathname === '/results') {
        handleResultsPage();
    }
});
