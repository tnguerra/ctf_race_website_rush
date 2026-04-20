const form = document.getElementById('login-form');
const message = document.getElementById('message');

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  message.textContent = 'Checking credentials...';

  const formData = new FormData(form);
  const response = await fetch('/api/login', {
    method: 'POST',
    body: formData,
  });

  if (response.ok) {
    const data = await response.json();
    window.location.href = data.redirect;
    return;
  }

  const error = await response.json().catch(() => ({ detail: 'Login failed' }));
  message.textContent = error.detail || 'Login failed';
});
