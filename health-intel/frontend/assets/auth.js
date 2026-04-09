
/* Auth Modal Logic */
const authOverlay = document.getElementById('auth-overlay');
const authSections = document.querySelectorAll('.auth-section');

function openAuth(sectionId) {
    authOverlay.classList.remove('hidden');
    showAuthSection(sectionId);
    document.body.style.overflow = 'hidden'; // Prevent background scrolling
}

function closeAuth() {
    authOverlay.classList.add('hidden');
    document.body.style.overflow = '';
}

function showAuthSection(sectionId) {
    // Hide all sections
    authSections.forEach(section => section.classList.add('hidden'));
    
    // Show target section
    const targetSection = document.getElementById(sectionId);
    if (targetSection) {
        targetSection.classList.remove('hidden');
    }
}

// Close on click outside
authOverlay.addEventListener('click', (e) => {
    if (e.target === authOverlay) {
        closeAuth();
    }
});
function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    const button = input.nextElementSibling.nextElementSibling?.tagName === 'BUTTON' 
        ? input.nextElementSibling.nextElementSibling 
        : input.parentElement.querySelector('.toggle-password');
        
    if (input.type === 'password') {
        input.type = 'text';
        button.textContent = '🙈';
    } else {
        input.type = 'password';
        button.textContent = '👁️';
    }
}

/* Signup Wizard Logic */
let currentSignupStep = 1;
const totalSignupSteps = 3;

function updateSignupProgress(step) {
    const steps = document.querySelectorAll('.progress-step');
    steps.forEach(s => {
        const sNum = parseInt(s.dataset.step);
        if (sNum <= step) {
            s.classList.add('active');
        } else {
            s.classList.remove('active');
        }
    });
}

function nextSignupStep(targetStep) {
    // Validate current step before moving
    if (!validateSignupStep(currentSignupStep)) {
        return;
    }

    document.getElementById(`signup-step-${currentSignupStep}`).classList.add('hidden');
    document.getElementById(`signup-step-${targetStep}`).classList.remove('hidden');
    
    currentSignupStep = targetStep;
    updateSignupProgress(currentSignupStep);
}

function prevSignupStep(targetStep) {
    document.getElementById(`signup-step-${currentSignupStep}`).classList.add('hidden');
    document.getElementById(`signup-step-${targetStep}`).classList.remove('hidden');
    
    currentSignupStep = targetStep;
    updateSignupProgress(currentSignupStep);
}

/* Validation System */
function showError(input, message) {
    const errorSpan = input.parentElement.querySelector('.error-msg');
    if (errorSpan) {
        errorSpan.textContent = message;
    }
    input.classList.add('error');
}

function clearError(input) {
    const errorSpan = input.parentElement.querySelector('.error-msg');
    if (errorSpan) {
        errorSpan.textContent = '';
    }
    input.classList.remove('error');
}

function validateEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function validateSignupStep(step) {
    let isValid = true;
    
    if (step === 1) {
        const email = document.getElementById('signup-email');
        const pass = document.getElementById('signup-password');
        const confirm = document.getElementById('signup-confirm-password');

        if (!validateEmail(email.value)) {
            showError(email, 'Please enter a valid email');
            isValid = false;
        } else {
            clearError(email);
        }

        if (pass.value.length < 8) {
            showError(pass, 'Password must be at least 8 characters');
            isValid = false;
        } else {
            clearError(pass);
        }

        if (pass.value !== confirm.value) {
            showError(confirm, 'Passwords do not match');
            isValid = false;
        } else {
            clearError(confirm);
        }
    } else if (step === 2) {
        const name = document.getElementById('signup-name');
        const dob = document.getElementById('signup-dob');

        if (!name.value.trim()) {
            showError(name, 'Name is required'); // Note: basic input styling might not support error for this layout yet, but logic is here
            name.classList.add('error');
            isValid = false;
        } else {
            name.classList.remove('error');
        }

        if (!dob.value) {
            dob.classList.add('error');
            isValid = false;
        } else {
            dob.classList.remove('error');
        }
    } else if (step === 3) {
        const terms = document.getElementById('signup-terms');
        if (!terms.checked) {
            // alert('You must agree to the terms'); // Better to show inline error, but for checkbox it's tricky
             terms.parentElement.style.color = 'red';
            isValid = false;
        } else {
             terms.parentElement.style.color = '';
        }
    }

    return isValid;
}

/* Password Strength Meter */
document.getElementById('signup-password').addEventListener('input', function(e) {
    const password = e.target.value;
    const bar = document.querySelector('.strength-bar');
    const text = document.querySelector('.strength-text');
    
    let strength = 0;
    if (password.length > 7) strength++;
    if (password.match(/[A-Z]/)) strength++;
    if (password.match(/[0-9]/)) strength++;
    if (password.match(/[^A-Za-z0-9]/)) strength++;

    switch(strength) {
        case 0:
        case 1:
            bar.style.width = '25%';
            bar.style.backgroundColor = '#ef4444'; // Red
            text.textContent = 'Weak';
            break;
        case 2:
            bar.style.width = '50%';
            bar.style.backgroundColor = '#fbbf24'; // Yellow
            text.textContent = 'Fair';
            break;
        case 3:
            bar.style.width = '75%';
            bar.style.backgroundColor = '#3b82f6'; // Blue
            text.textContent = 'Good';
            break;
        case 4:
            bar.style.width = '100%';
            bar.style.backgroundColor = '#22c55e'; // Green
            text.textContent = 'Strong';
            break;
    }
});

/* Form Submissions (Mock) */
document.getElementById('login-form').addEventListener('submit', (e) => {
    e.preventDefault();
    // Simulate login
    // In a real app, you'd fetch API here
    alert('Login successful! Redirecting...');
    closeAuth();
});

document.getElementById('signup-form').addEventListener('submit', (e) => {
    e.preventDefault();
    if (validateSignupStep(3)) {
        // Show success screen (mock email verification)
        showAuthSection('auth-success');
        document.getElementById('success-message').textContent = 'Account created! Please check your email to verify.';
    }
});

function handleForgotSubmit(e) {
    e.preventDefault();
    showAuthSection('auth-verify-code');
}

function handleVerifySubmit(e) {
    e.preventDefault();
    showAuthSection('auth-reset-password');
}

function handleResetSubmit(e) {
    e.preventDefault();
    showAuthSection('auth-success');
    document.getElementById('success-message').textContent = 'Password reset successfully.';
}
