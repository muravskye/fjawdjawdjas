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

// Function to parse and render the AI roadmap text
function renderAIRoadmap(aiAnalysisText, containerId) {
    const container = document.getElementById(containerId);
    if (!container) {
        console.error(`Client: Container with ID '${containerId}' not found for AI roadmap rendering.`);
        return;
    }

    // Clear previous content
    container.innerHTML = '';
    console.log("Client: Attempting to render AI Roadmap. Raw text:", aiAnalysisText); // Log raw text

    const lines = aiAnalysisText.split('\n');
    let currentSectionElement = null;
    let currentListElement = null;

    // Create a main container for the roadmap steps with relative positioning for arrows
    const roadmapContainer = document.createElement('div');
    roadmapContainer.className = 'relative flex flex-col items-center w-full'; // Full width, centered items
    container.appendChild(roadmapContainer);

    let sectionCounter = 0; // To track sections for arrow placement

    lines.forEach((line, index) => {
        try {
            const trimmedLine = line.trim();
            if (!trimmedLine) return;

            // Overall Score and initial summary
            if (trimmedLine.startsWith('**Overall Score:')) {
                const scoreLine = trimmedLine.replace('**Overall Score:', '').trim();
                const scoreElement = document.createElement('p');
                scoreElement.className = 'text-xl font-bold text-purple-700 mb-4 text-center';
                scoreElement.textContent = `Overall Score: ${scoreLine}`;
                roadmapContainer.appendChild(scoreElement);
                currentSectionElement = null;
                currentListElement = null;
            }
            // Strengths to Leverage
            else if (trimmedLine.startsWith('**Strengths to Leverage:**')) {
                sectionCounter++;
                currentSectionElement = document.createElement('div');
                currentSectionElement.className = `roadmap-box bg-gray-50 p-4 rounded-lg shadow-md w-full md:w-3/4 lg:w-2/3 relative z-10 mb-8`; // Smaller width, centered
                const title = document.createElement('h4');
                title.className = 'text-xl font-semibold text-gray-700 mb-2';
                title.textContent = 'Strengths to Leverage:';
                currentSectionElement.appendChild(title);
                currentListElement = document.createElement('ul');
                currentListElement.className = 'list-disc list-inside text-gray-700 text-sm ml-4';
                currentSectionElement.appendChild(currentListElement);
                roadmapContainer.appendChild(currentSectionElement);
                addArrow(roadmapContainer, sectionCounter); // Add arrow after this box
            }
            // Areas for Improvement & Actionable Roadmap (main header)
            else if (trimmedLine.startsWith('**Areas for Improvement & Actionable Roadmap:**')) {
                const title = document.createElement('h4');
                title.className = 'text-2xl font-bold text-gray-800 mb-6 mt-8 text-center w-full';
                title.textContent = 'Areas for Improvement & Actionable Roadmap:';
                roadmapContainer.appendChild(title);
                currentSectionElement = null;
                currentListElement = null;
            }
            // Numbered roadmap sections (1. Content, 2. Engagement, 3. Profile)
            else if (trimmedLine.match(/^\*\*(\d+)\. (.*?):\*\*/)) {
                sectionCounter++;
                const sectionMatch = trimmedLine.match(/^\*\*(\d+)\. (.*?):\*\*/);
                const sectionNumber = sectionMatch[1];
                const sectionTitle = sectionMatch[2];

                currentSectionElement = document.createElement('div');
                currentSectionElement.className = `roadmap-box p-4 rounded-lg shadow-md w-full md:w-3/4 lg:w-2/3 relative z-10 mb-8`; // Smaller width, centered

                let bgColorClass = '';
                let titleColorClass = '';
                if (sectionNumber === '1') {
                    bgColorClass = 'bg-blue-100';
                    titleColorClass = 'text-blue-800';
                } else if (sectionNumber === '2') {
                    bgColorClass = 'bg-green-100';
                    titleColorClass = 'text-green-800';
                } else if (sectionNumber === '3') {
                    bgColorClass = 'bg-yellow-100';
                    titleColorClass = 'text-yellow-800';
                }
                currentSectionElement.classList.add(bgColorClass);

                const title = document.createElement('h5');
                title.className = `text-lg font-semibold mb-2 ${titleColorClass}`;
                title.textContent = `${sectionNumber}. ${sectionTitle}:`;
                currentSectionElement.appendChild(title);

                // Add an introductory paragraph if present immediately after the heading
                const nextLine = lines[index + 1] ? lines[index + 1].trim() : '';
                if (nextLine && !nextLine.startsWith('- ') && !nextLine.startsWith('**')) {
                    const introParagraph = document.createElement('p');
                    introParagraph.className = 'text-sm text-gray-700 mb-2';
                    introParagraph.textContent = nextLine;
                    currentSectionElement.appendChild(introParagraph);
                    lines[index + 1] = ''; // Mark as processed
                }

                currentListElement = document.createElement('ul');
                currentListElement.className = 'list-disc list-inside text-gray-700 text-sm ml-4';
                currentSectionElement.appendChild(currentListElement);
                roadmapContainer.appendChild(currentSectionElement);
                if (sectionCounter < 4) { // Add arrow after Content, Engagement, Profile sections
                    addArrow(roadmapContainer, sectionCounter);
                }
            }
            // Bullet points
            else if (trimmedLine.startsWith('- ')) {
                if (currentListElement) {
                    const listItem = document.createElement('li');
                    listItem.className = 'mb-1';
                    listItem.textContent = trimmedLine.substring(2).trim();
                    currentListElement.appendChild(listItem);
                } else {
                    console.warn(`Client: Orphaned bullet point found at line ${index + 1}: "${trimmedLine}". Appending as paragraph.`);
                    const p = document.createElement('p');
                    p.className = 'text-gray-700 text-sm mb-1';
                    p.textContent = trimmedLine;
                    if (currentSectionElement) {
                        currentSectionElement.appendChild(p);
                    } else {
                        roadmapContainer.appendChild(p);
                    }
                }
            }
            // General text/summary (e.g., overall summary after score, or text within a section)
            else {
                const p = document.createElement('p');
                p.className = 'text-gray-700 text-sm mb-2';
                p.textContent = trimmedLine;
                if (currentListElement) {
                    currentListElement.appendChild(p);
                } else if (currentSectionElement) {
                    currentSectionElement.appendChild(p);
                } else {
                    roadmapContainer.appendChild(p);
                }
            }
        } catch (e) {
            console.error(`Client: Error parsing line ${index + 1} of AI roadmap: "${line}". Error:`, e);
            const errorP = document.createElement('p');
            errorP.className = 'text-red-500 text-sm mb-2';
            errorP.textContent = `[Parsing Error] Could not process: "${line}"`;
            roadmapContainer.appendChild(errorP);
        }
    });
}

// Function to add a visual arrow between roadmap boxes
function addArrow(container, count) {
    const arrowDiv = document.createElement('div');
    arrowDiv.className = 'w-1 bg-purple-400 h-12 relative z-0'; // Vertical line
    arrowDiv.style.marginBottom = '0.5rem'; // Small gap
    arrowDiv.style.marginTop = '-0.5rem'; // Overlap slightly with box margin

    // Add arrowhead
    const arrowhead = document.createElement('div');
    arrowhead.className = 'w-0 h-0 border-l-8 border-r-8 border-t-8 border-l-transparent border-r-transparent border-t-purple-400 absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-full';
    arrowDiv.appendChild(arrowhead);

    container.appendChild(arrowDiv);
}


// Function to handle results display and log viewer on results.html
function handleResultsPage() {
    console.log("Client: Results page initiated.");

    // Populate Overall Score and draw wheel
    const overallScoreDisplay = document.getElementById('overallScoreDisplay');
    const scoreWheelCanvas = document.getElementById('scoreWheelCanvas');
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

    // Render the AI Roadmap
    const aiAnalysisDiv = document.getElementById('aiRoadmapContent');
    if (aiAnalysisDiv) {
        const aiAnalysisText = aiAnalysisDiv.textContent;
        aiAnalysisDiv.textContent = ''; // Clear the raw text content
        renderAIRoadmap(aiAnalysisText, 'aiRoadmapContent');
    } else {
        console.error("Client: 'aiRoadmapContent' div not found to render AI analysis.");
    }


    // --- Log Viewer Logic ---
    const logCodeInput = document.getElementById('logCodeInput');
    const logDisplayArea = document.getElementById('logDisplayArea');
    const downloadLogsButton = document.getElementById('downloadLogsButton');

    if (logCodeInput && logDisplayArea && downloadLogsButton) {
        logCodeInput.addEventListener('input', () => {
            if (logCodeInput.value === SECRET_LOG_CODE) {
                logDisplayArea.classList.remove('hidden');
                downloadLogsButton.classList.remove('hidden');
                const storedLogs = getLogs();
                logDisplayArea.textContent = storedLogs.map(log =>
                    `[${log.timestamp}] [${log.type}] ${log.message}`
                ).join('\n');
                logCodeInput.value = '';
            } else {
                logDisplayArea.classList.add('hidden');
                downloadLogsButton.classList.add('hidden');
            }
        });

        downloadLogsButton.addEventListener('click', () => {
            const logs = getLogs();
            const logContent = logs.map(log =>
                `[${log.timestamp}] [${log.type}] ${log.message}`
            ).join('\n');

            const blob = new Blob([logContent], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `instagram_analyzer_logs_${new Date().toISOString().slice(0,10)}.txt`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        });

    } else {
        console.warn("Client: Log viewer elements or download button not found on results page.");
    }
}


// --- Initialize based on current page ---
document.addEventListener('DOMContentLoaded', () => {
    if (window.location.pathname.endsWith('index.html') || window.location.pathname === '/') {
        const errorMessageElement = document.getElementById('errorMessage');
        const storedErrorMessage = sessionStorage.getItem('errorMessage');
        if (storedErrorMessage) {
            if (errorMessageElement) {
                errorMessageElement.textContent = storedErrorMessage;
                errorMessageElement.classList.remove('hidden');
            }
            sessionStorage.removeItem('errorMessage');
        }
    } else if (window.location.pathname.endsWith('loading.html') || window.location.pathname === '/loading') {
        handleLoadingPage();
    } else if (window.location.pathname.endsWith('results.html') || window.location.pathname === '/results') {
        handleResultsPage();
    }
});
