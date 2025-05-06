// Main JavaScript for Sentinel SI Interface

document.addEventListener('DOMContentLoaded', function() {
  // Handle SI interaction form submission
  const interactionForm = document.getElementById('interaction-form');
  if (interactionForm) {
    interactionForm.addEventListener('submit', function(event) {
      event.preventDefault();
      
      const siId = this.getAttribute('data-si-id');
      const userInput = document.getElementById('user-input').value.trim();
      const messagesContainer = document.getElementById('si-messages');
      
      if (userInput === '') {
        return;
      }
      
      // Add user message to the conversation
      const userMessageElement = document.createElement('div');
      userMessageElement.className = 'si-message user-message';
      userMessageElement.innerHTML = `<p class="mb-1"><strong>You:</strong></p><p>${userInput}</p>`;
      messagesContainer.appendChild(userMessageElement);
      
      // Clear input field
      document.getElementById('user-input').value = '';
      
      // Scroll to bottom of messages
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
      
      // Show loading indicator
      const loadingElement = document.createElement('div');
      loadingElement.className = 'si-message si-response';
      loadingElement.innerHTML = `<p class="mb-1"><strong>SI:</strong></p><p><em>Processing response...</em></p>`;
      messagesContainer.appendChild(loadingElement);
      
      // Send the request to the server
      fetch(`/si/${siId}/interact`, {
        method: 'POST',
        body: new FormData(interactionForm),
        headers: {
          'X-Requested-With': 'XMLHttpRequest'
        }
      })
      .then(response => response.json())
      .then(data => {
        // Remove loading indicator
        messagesContainer.removeChild(loadingElement);
        
        // Add SI response to the conversation
        const siResponseElement = document.createElement('div');
        siResponseElement.className = 'si-message si-response';
        siResponseElement.innerHTML = `<p class="mb-1"><strong>SI:</strong></p><p>${data.response}</p>`;
        messagesContainer.appendChild(siResponseElement);
        
        // Scroll to bottom of messages
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
      })
      .catch(error => {
        console.error('Error:', error);
        
        // Remove loading indicator
        messagesContainer.removeChild(loadingElement);
        
        // Show error message
        const errorElement = document.createElement('div');
        errorElement.className = 'si-message si-response text-danger';
        errorElement.innerHTML = `<p class="mb-1"><strong>Error:</strong></p><p>Failed to process your request. Please try again.</p>`;
        messagesContainer.appendChild(errorElement);
        
        // Scroll to bottom of messages
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
      });
    });
  }
  
  // Handle access code form visibility toggle
  const codeToggleBtn = document.getElementById('code-toggle-btn');
  const codeForm = document.getElementById('access-code-form');
  
  if (codeToggleBtn && codeForm) {
    codeToggleBtn.addEventListener('click', function() {
      if (codeForm.classList.contains('d-none')) {
        codeForm.classList.remove('d-none');
        codeToggleBtn.textContent = 'Hide Access Code Form';
      } else {
        codeForm.classList.add('d-none');
        codeToggleBtn.textContent = 'Have an Access Code?';
      }
    });
  }
  
  // Bootstrap Tooltips Initialization
  const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
  if (tooltipTriggerList.length > 0) {
    [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
  }
  
  // Handle confirmation modals
  const confirmationBtns = document.querySelectorAll('[data-confirm]');
  
  confirmationBtns.forEach(btn => {
    btn.addEventListener('click', function(event) {
      if (!confirm(this.getAttribute('data-confirm'))) {
        event.preventDefault();
      }
    });
  });
});
