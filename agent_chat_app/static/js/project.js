/* Project specific Javascript goes here. */

// Enhanced Chat Interface JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Auto-scroll to bottom with smooth animation
    function smoothScrollToBottom() {
        const chatMessages = document.getElementById('chat-messages');
        if (chatMessages) {
            chatMessages.scrollTo({
                top: chatMessages.scrollHeight,
                behavior: 'smooth'
            });
        }
    }

    // Add typing indicator with animation
    function addTypingIndicator() {
        const existingIndicator = document.getElementById('typing-indicator');
        if (existingIndicator) return;
        
        const chatMessages = document.getElementById('chat-messages');
        const indicatorHtml = `
            <div id="typing-indicator" class="mb-3" style="animation: messageSlideIn 0.5s ease-out;">
                <div class="d-flex align-items-start">
                    <div class="me-auto" style="max-width: 80%;">
                        <div class="bg-white border rounded-3 p-3 shadow-sm">
                            <div class="d-flex align-items-center mb-2">
                                <div class="bg-primary bg-opacity-10 rounded-circle p-1 me-2">
                                    <i class="fas fa-robot text-primary" style="font-size: 0.8em;"></i>
                                </div>
                                <strong class="small">AI Assistant</strong>
                            </div>
                            <div class="typing-animation">
                                <span></span><span></span><span></span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        if (chatMessages) {
            chatMessages.insertAdjacentHTML('beforeend', indicatorHtml);
            smoothScrollToBottom();
        }
    }

    // Remove typing indicator
    function removeTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.remove();
        }
    }

    // Enhanced message input with auto-resize
    const messageInput = document.querySelector('input[name="message"]');
    if (messageInput) {
        messageInput.addEventListener('input', function() {
            // Auto-resize logic could be added here for textarea
            this.style.height = 'auto';
            this.style.height = this.scrollHeight + 'px';
        });

        // Enter key handling with shift support
        messageInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                const form = this.closest('form');
                if (form && this.value.trim()) {
                    // Show typing indicator before sending
                    addTypingIndicator();
                    form.submit();
                }
            }
        });
    }

    // Enhanced hover effects for conversation items
    const conversationItems = document.querySelectorAll('.list-group-item-action');
    conversationItems.forEach(item => {
        item.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-2px) translateX(4px)';
        });
        
        item.addEventListener('mouseleave', function() {
            if (!this.classList.contains('active')) {
                this.style.transform = 'translateY(0) translateX(0)';
            }
        });
    });

    // Smooth scroll to bottom on page load
    setTimeout(smoothScrollToBottom, 300);

    // Add visual feedback for form submission
    const chatForm = document.querySelector('form[method="post"]');
    if (chatForm) {
        chatForm.addEventListener('submit', function(e) {
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                submitBtn.disabled = true;
            }
        });
    }

    // Enhanced dropdown animations
    document.addEventListener('shown.bs.dropdown', function(e) {
        const dropdown = e.target.nextElementSibling;
        if (dropdown) {
            dropdown.style.animation = 'fadeInDown 0.3s ease-out';
        }
    });

    // Mobile sidebar toggle
    const sidebarToggle = document.querySelector('.navbar-toggler');
    const sidebar = document.querySelector('.chat-container .col-md-3');
    
    if (sidebarToggle && sidebar && window.innerWidth <= 768) {
        sidebarToggle.addEventListener('click', function() {
            sidebar.classList.toggle('show');
        });
        
        // Close sidebar when clicking outside on mobile
        document.addEventListener('click', function(e) {
            if (window.innerWidth <= 768) {
                if (!sidebar.contains(e.target) && !sidebarToggle.contains(e.target)) {
                    sidebar.classList.remove('show');
                }
            }
        });
    }
});

// CSS animations for typing indicator
const typingStyles = `
.typing-animation {
    display: flex;
    align-items: center;
    height: 20px;
}

.typing-animation span {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: #6c757d;
    margin: 0 2px;
    opacity: 0.4;
    animation: typing 1.4s infinite ease-in-out;
}

.typing-animation span:nth-child(1) { animation-delay: 0s; }
.typing-animation span:nth-child(2) { animation-delay: 0.2s; }
.typing-animation span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
    0%, 60%, 100% {
        transform: translateY(0);
        opacity: 0.4;
    }
    30% {
        transform: translateY(-10px);
        opacity: 1;
    }
}

@keyframes fadeInDown {
    from {
        opacity: 0;
        transform: translateY(-10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* Enhanced message animations */
@keyframes messageSlideIn {
    from {
        opacity: 0;
        transform: translateY(20px) scale(0.95);
    }
    to {
        opacity: 1;
        transform: translateY(0) scale(1);
    }
}
`;

// Inject typing styles
const styleSheet = document.createElement('style');
styleSheet.textContent = typingStyles;
document.head.appendChild(styleSheet);
