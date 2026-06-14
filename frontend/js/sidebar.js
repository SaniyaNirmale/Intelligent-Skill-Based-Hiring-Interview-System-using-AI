document.addEventListener('DOMContentLoaded', () => {
    const userString = sessionStorage.getItem('wci_user');
    const sidebar = document.getElementById('sidebar');
    
    // Auth Check
    if (!userString) {
        const publicPages = ['/index.html', '/login-candidate.html', '/login-recruiter.html', '/register.html'];
        const isPublic = publicPages.some(page => window.location.pathname.endsWith(page));
        
        if (!isPublic && window.location.pathname !== '/' && !window.location.pathname.endsWith('index.html')) {
            window.location.href = window.location.pathname.includes('/candidate/') || window.location.pathname.includes('/recruiter/') ? '../index.html' : 'index.html';
            return;
        }
    } else {
        const user = JSON.parse(userString);
        
        // Role Guard
        const path = window.location.pathname;
        if (path.includes('/candidate/') && user.role !== 'candidate') {
            if (user.role === 'recruiter' && path.endsWith('/candidate/report.html')) {
                window.location.href = `../recruiter/report.html${window.location.search}`;
                return;
            }
            window.location.href = '../index.html';
            return;
        }
        if (path.includes('/recruiter/') && user.role !== 'recruiter') {
            window.location.href = '../index.html';
            return;
        }

        populateSidebar(user);
    }

    // Sidebar State (Collapse)
    const isCollapsed = localStorage.getItem('sidebar_collapsed') === 'true';
    if (isCollapsed) {
        sidebar.classList.add('collapsed');
    }

    // Active Link Highlighting
    highlightActiveLink();
});

function populateSidebar(user) {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;

    const isCandidate = user.role === 'candidate';
    const links = isCandidate ? [
        { href: 'dashboard.html', text: 'Dashboard', icon: '📊' },
        { href: 'resume.html', text: 'Resume & Skills', icon: '📄' },
        { href: 'jobs.html', text: 'Job Openings', icon: '💼' },
        { href: 'available-interviews.html', text: 'Company Interviews', icon: '🏢' },
        { href: 'practice-interview.html', text: 'Practice Interview', icon: '🎙️' },
        { href: 'coding-test.html', text: 'Coding Assessment', icon: '💻' },
        { href: 'skill-graph.html', text: 'Skill Graph', icon: '🕸️' },
        { href: 'analytics.html', text: 'My Results', icon: '🏆' },
        { href: 'recommendations.html', text: 'Learning Path', icon: '🎓' }
    ] : [
        { href: 'dashboard.html', text: 'Dashboard', icon: '📊' },
        { href: 'candidates.html', text: 'Candidates', icon: '👥' },
        { href: 'jobs.html', text: 'Manage Jobs', icon: '💼' },
        { href: 'live-monitor.html', text: 'Live Monitor', icon: '🔴' },
        { href: 'reports.html', text: 'Reports', icon: '📁' },
        { href: 'analytics.html', text: 'Analytics', icon: '📈' },
        { href: 'settings.html', text: 'Settings', icon: '⚙️' }
    ];

    sidebar.innerHTML = `
        <div class="sidebar-logo">
            <span class="logo-main">WCI Engine</span>
            <span class="logo-sub">Workforce Credibility Index</span>
        </div>
        <nav class="nav-list">
            ${links.map(link => `
                <a href="${link.href}" class="nav-link">
                    <span class="nav-icon">${link.icon}</span>
                    <span class="nav-label">${link.text}</span>
                </a>
            `).join('')}
        </nav>
        <div class="sidebar-footer">
            <div class="user-profile">
                <div class="user-avatar">${user.name.charAt(0).toUpperCase()}</div>
                <div class="user-info">
                    <span class="user-name">${user.name}</span>
                    <span class="user-role">${user.role.charAt(0).toUpperCase() + user.role.slice(1)}</span>
                </div>
            </div>
            <button class="btn logout-btn" onclick="handleLogout()">Logout</button>
        </div>
    `;
}

function highlightActiveLink() {
    const currentPath = window.location.pathname;
    const currentSearch = window.location.search;
    const navLinks = document.querySelectorAll('.nav-link');

    navLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (href.includes('?')) {
            const [pathPart, searchPart] = href.split('?');
            if (currentPath.endsWith(pathPart) && currentSearch.includes(searchPart)) {
                link.classList.add('active');
            }
        } else {
            if (currentPath.endsWith(href) || (href === 'available-interviews.html' && currentPath.endsWith('official-interview.html'))) {
                if (href === 'dashboard.html' && currentSearch.includes('view=official')) {
                    // Do not highlight the base dashboard link when viewing official interviews
                    return;
                }
                link.classList.add('active');
            }
        }
    });
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('collapsed');
    localStorage.setItem('sidebar_collapsed', sidebar.classList.contains('collapsed'));
}

function handleLogout() {
    sessionStorage.removeItem('wci_user');
    // Go up one level to index.html since we're in /candidate/ or /recruiter/
    window.location.href = '../index.html';
}
