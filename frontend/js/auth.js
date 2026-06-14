async function handleLogin(e, role) {
    e.preventDefault();
    const form = e.target;
    const email = form.email.value;
    const password = form.password.value;
    const errorEl = document.getElementById('error-message');
    const submitBtn = form.querySelector('button[type="submit"]');

    // Reset error
    if (errorEl) {
        errorEl.textContent = '';
        errorEl.style.display = 'none';
    }

    // Show loading
    const originalBtnText = submitBtn.innerHTML;
    submitBtn.innerHTML = '<div class="loading-spinner"></div>';
    submitBtn.disabled = true;

    try {
        const result = await apiRequest('/auth/login', 'POST', { email, password, role });
        
        // Success
        sessionStorage.setItem('wci_user', JSON.stringify({
            user_id: result.user_id,
            name: result.name,
            email: result.email,
            role: result.role
        }));

        // Redirect
        if (result.role === 'candidate') {
            window.location.href = 'candidate/dashboard.html';
        } else {
            window.location.href = 'recruiter/dashboard.html';
        }
    } catch (err) {
        if (errorEl) {
            errorEl.textContent = err.message;
            errorEl.style.display = 'flex';
        }
    } finally {
        submitBtn.innerHTML = originalBtnText;
        submitBtn.disabled = false;
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const form = e.target;
    const name = form.fullname.value;
    const email = form.email.value;
    const password = form.password.value;
    const confirmPassword = form.confirm_password.value;
    const role = document.querySelector('input[name="role"]:checked').value;
    const errorEl = document.getElementById('error-message');
    const submitBtn = form.querySelector('button[type="submit"]');

    if (password !== confirmPassword) {
        errorEl.textContent = 'Passwords do not match';
        errorEl.style.display = 'flex';
        return;
    }

    // Show loading
    const originalBtnText = submitBtn.innerHTML;
    submitBtn.innerHTML = '<div class="loading-spinner"></div>';
    submitBtn.disabled = true;

    try {
        await apiRequest('/auth/register', 'POST', { name, email, password, role });
        // Redirect to login based on role
        if (role === 'candidate') {
            window.location.href = 'login-candidate.html';
        } else {
            window.location.href = 'login-recruiter.html';
        }
    } catch (err) {
        if (errorEl) {
            errorEl.textContent = err.message;
            errorEl.style.display = 'flex';
        }
    } finally {
        submitBtn.innerHTML = originalBtnText;
        submitBtn.disabled = false;
    }
}

// Password toggle
function togglePassword(id) {
    const input = document.getElementById(id);
    if (input.type === 'password') {
        input.type = 'text';
    } else {
        input.type = 'password';
    }
}

