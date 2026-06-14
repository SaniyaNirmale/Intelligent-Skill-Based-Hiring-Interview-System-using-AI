// Automatically point the API to the same IP address the frontend is being served from
const BASE_URL = `${window.location.protocol}//${window.location.hostname}:8000`;

/**
 * Core API Request Helper
 */
async function apiRequest(path, method = "GET", body = null, isFile = false) {
    const headers = {};
    if (!isFile) {
        headers["Content-Type"] = "application/json";
    }

    const config = {
        method,
        headers,
    };

    if (body) {
        config.body = isFile ? body : JSON.stringify(body);
    }

    try {
        const response = await fetch(`${BASE_URL}${path}`, config);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || data.error || "An unexpected error occurred");
        }

        return data;
    } catch (error) {
        console.error(`API Error [${method} ${path}]:`, error);
        throw error;
    }
}

// --- API MODULES ---

const api = {
    // AUTH
    auth: {
        login: (email, password, role) => apiRequest("/auth/login", "POST", { email, password, role }),
        register: (name, email, password, role) => apiRequest("/auth/register", "POST", { name, email, password, role }),
        getMe: (user_id, role) => apiRequest(`/auth/me?user_id=${user_id}&role=${role}`),
    },

    // RESUME
    resume: {
        uploadResume: (file, candidate_id) => {
            const formData = new FormData();
            formData.append("file", file);
            formData.append("candidate_id", candidate_id);
            return apiRequest("/resume/upload", "POST", formData, true);
        },
        getResume: (candidate_id) => apiRequest(`/resume/${candidate_id}`),
    },

    // INTERVIEW
    interview: {
        startInterview: (candidate_id, skills) => apiRequest("/interview/start", "POST", { candidate_id, skills }),
        submitAnswer: (session_id, answer_text, time_taken) => 
            apiRequest("/interview/answer", "POST", { session_id, answer_text, time_taken_seconds: time_taken }),
        resumeInterview: (session_id) => apiRequest("/interview/resume", "POST", { session_id }),
    },

    // REPORTS
    reports: {
        generateReport: (session_id) => apiRequest("/report/generate", "POST", { session_id }),
        getReport: (report_id) => apiRequest(`/report/${report_id}`),
    },

    // CANDIDATE MODULES
    candidate: {
        getDashboard: (candidate_id) => apiRequest(`/candidate/dashboard/${candidate_id}`),
        getAnalytics: (candidate_id, range) => apiRequest(`/candidate/analytics/${candidate_id}?range=${range}`),
        getSkillGraph: (candidate_id) => apiRequest(`/candidate/skill-graph/${candidate_id}`),
        getRecommendations: (candidate_id) => apiRequest(`/candidate/recommendations/${candidate_id}`),
        getLearningPath: (candidate_id) => apiRequest(`/candidate/learning-path/${candidate_id}`),
    },

    // RECRUITER MODULES
    recruiter: {
        getDashboard: (recruiter_id) => apiRequest(`/recruiter/dashboard/${recruiter_id}`),
        getCandidates: () => apiRequest("/recruiter/candidates"),
        getReports: (page = 1) => apiRequest(`/recruiter/reports?page=${page}`),
        getActiveSessions: () => apiRequest("/recruiter/active-sessions"),
        getSessionLive: (session_id) => apiRequest(`/recruiter/session/${session_id}/live`),
        flagSession: (session_id) => apiRequest(`/recruiter/flag-session/${session_id}`, "POST"),
    }
};

// Global export for vanilla JS
window.api = api;
window.apiRequest = apiRequest; // Backward compatibility with previous script versions
