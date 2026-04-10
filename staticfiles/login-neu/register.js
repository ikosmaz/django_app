class NeumorphismRegisterForm {
    constructor() {
        this.form = document.getElementById('registerForm');
        this.usernameInput = document.getElementById('username');
        this.emailInput = document.getElementById('email');
        this.password1Input = document.getElementById('password1');
        this.password2Input = document.getElementById('password2');
        this.submitButton = this.form.querySelector('.login-btn');

        this.init();
    }

    init() {
        this.bindEvents();
        this.setupPasswordToggle('passwordToggle1', this.password1Input);
        this.setupPasswordToggle('passwordToggle2', this.password2Input);
    }

    bindEvents() {
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));

        [this.usernameInput, this.emailInput, this.password1Input, this.password2Input].forEach((input) => {
            input.addEventListener('focus', (e) => this.addSoftPress(e));
            input.addEventListener('blur', (e) => this.removeSoftPress(e));
        });

        this.usernameInput.addEventListener('input', () => this.clearError('username'));
        this.emailInput.addEventListener('input', () => this.clearError('email'));
        this.password1Input.addEventListener('input', () => this.clearError('password1'));
        this.password2Input.addEventListener('input', () => this.clearError('password2'));
    }

    setupPasswordToggle(toggleId, inputEl) {
        const btn = document.getElementById(toggleId);
        if (!btn || !inputEl) return;

        btn.addEventListener('click', () => {
            const type = inputEl.type === 'password' ? 'text' : 'password';
            inputEl.type = type;
            btn.classList.toggle('show-password', type === 'text');
            this.animateSoftPress(btn);
        });
    }

    addSoftPress(e) {
        const inputGroup = e.target.closest('.neu-input');
        if (inputGroup) inputGroup.style.transform = 'scale(0.98)';
    }

    removeSoftPress(e) {
        const inputGroup = e.target.closest('.neu-input');
        if (inputGroup) inputGroup.style.transform = 'scale(1)';
    }

    animateSoftPress(element) {
        element.style.transform = 'scale(0.95)';
        setTimeout(() => {
            element.style.transform = 'scale(1)';
        }, 150);
    }

    validateUsername() {
        const value = this.usernameInput.value.trim();
        if (!value) {
            this.showError('username', 'Username is required');
            return false;
        }
        this.clearError('username');
        return true;
    }

    validateEmail() {
        const value = this.emailInput.value.trim();
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!value) {
            this.showError('email', 'Email is required');
            return false;
        }
        if (!emailRegex.test(value)) {
            this.showError('email', 'Please enter a valid email');
            return false;
        }
        this.clearError('email');
        return true;
    }

    validatePasswords() {
        let ok = true;
        if (!this.password1Input.value) {
            this.showError('password1', 'Password is required');
            ok = false;
        } else {
            this.clearError('password1');
        }

        if (!this.password2Input.value) {
            this.showError('password2', 'Please confirm password');
            ok = false;
        } else if (this.password1Input.value !== this.password2Input.value) {
            this.showError('password2', 'Passwords do not match');
            ok = false;
        } else {
            this.clearError('password2');
        }

        return ok;
    }

    showError(field, message) {
        const input = document.getElementById(field);
        const formGroup = input ? input.closest('.form-group') : null;
        const errorElement = document.getElementById(`${field}Error`);
        if (formGroup) formGroup.classList.add('error');
        if (errorElement) {
            errorElement.textContent = message;
            errorElement.classList.add('show');
        }
    }

    clearError(field) {
        const input = document.getElementById(field);
        const formGroup = input ? input.closest('.form-group') : null;
        const errorElement = document.getElementById(`${field}Error`);
        if (formGroup) formGroup.classList.remove('error');
        if (errorElement) {
            errorElement.classList.remove('show');
            setTimeout(() => {
                errorElement.textContent = '';
            }, 250);
        }
    }

    handleSubmit(e) {
        const ok = this.validateUsername() && this.validateEmail() && this.validatePasswords();
        if (!ok) {
            e.preventDefault();
            this.animateSoftPress(this.submitButton);
            return;
        }

        this.submitButton.classList.toggle('loading', true);
        this.submitButton.disabled = true;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new NeumorphismRegisterForm();
});
