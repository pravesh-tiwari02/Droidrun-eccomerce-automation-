// PriceHunter - Main Application Logic

class PriceHunter {
    constructor() {
        this.currentTaskId = null;
        this.currentProduct = null;
        this.ws = null;
        this.results = {};

        this.initElements();
        this.bindEvents();
    }

    initElements() {
        // Search
        this.productInput = document.getElementById('productInput');
        this.searchBtn = document.getElementById('searchBtn');
        this.btnText = this.searchBtn.querySelector('.btn-text');
        this.btnLoader = this.searchBtn.querySelector('.btn-loader');

        // Sections
        this.statusSection = document.getElementById('statusSection');
        this.statusTitle = document.getElementById('statusTitle');
        this.statusMessage = document.getElementById('statusMessage');
        this.resultsSection = document.getElementById('resultsSection');
        this.bestDeal = document.getElementById('bestDeal');

        // Cards
        this.priceCards = document.querySelectorAll('.price-card');

        // Best deal elements
        this.bestApp = document.getElementById('bestApp');
        this.bestPrice = document.getElementById('bestPrice');
        this.bestAppBtn = document.getElementById('bestAppBtn');
        this.buyBestBtn = document.getElementById('buyBestBtn');

        // Order modal
        this.orderModal = document.getElementById('orderModal');
        this.orderApp = document.getElementById('orderApp');
        this.orderProduct = document.getElementById('orderProduct');
        this.cancelOrder = document.getElementById('cancelOrder');
        this.confirmOrder = document.getElementById('confirmOrder');

        // Order status modal
        this.orderStatusModal = document.getElementById('orderStatusModal');
        this.orderStatusTitle = document.getElementById('orderStatusTitle');
        this.orderStatusMsg = document.getElementById('orderStatusMsg');
    }

    bindEvents() {
        // Search
        this.searchBtn.addEventListener('click', () => this.startSearch());
        this.productInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.startSearch();
        });

        // Buy buttons
        document.querySelectorAll('.btn-buy').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const app = e.target.dataset.app;
                this.showOrderModal(app);
            });
        });

        this.buyBestBtn.addEventListener('click', () => {
            if (this.results.best) {
                this.showOrderModal(this.results.best.app);
            }
        });

        // Modal
        this.cancelOrder.addEventListener('click', () => this.hideOrderModal());
        document.querySelector('.modal-close').addEventListener('click', () => this.hideOrderModal());
        this.confirmOrder.addEventListener('click', () => this.placeOrder());
    }

    async startSearch() {
        const product = this.productInput.value.trim();
        if (!product) {
            this.productInput.focus();
            return;
        }

        this.currentProduct = product;
        this.results = {};

        // Update UI
        this.setSearchLoading(true);
        this.showStatus('Connecting to your phone...', 'Starting search...');
        this.resultsSection.classList.remove('hidden');
        this.resetCards();
        this.bestDeal.classList.add('hidden');

        try {
            // Start search
            const response = await fetch('/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ product })
            });

            const data = await response.json();
            this.currentTaskId = data.task_id;

            // Connect WebSocket for real-time updates
            this.connectWebSocket(data.task_id);

        } catch (error) {
            console.error('Search error:', error);
            this.showStatus('Connection failed', 'Could not connect to server. Is it running?');
            this.setSearchLoading(false);
        }
    }

    connectWebSocket(taskId) {
        const wsUrl = `ws://${window.location.host}/ws/${taskId}`;
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
        };

        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleUpdate(data);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        this.ws.onclose = () => {
            console.log('WebSocket closed');
        };
    }

    handleUpdate(data) {
        console.log('Update:', data);

        if (data.current_app) {
            this.showStatus(
                `Searching on ${this.capitalize(data.current_app)}...`,
                `Your phone is searching ${data.current_app.toUpperCase()} for "${this.currentProduct}"`
            );
            this.setCardSearching(data.current_app);
        }

        if (data.app_complete && data.result) {
            this.updateCard(data.app_complete, data.result);
        }

        if (data.status === 'completed') {
            this.handleSearchComplete(data);
        }
    }

    handleSearchComplete(data) {
        this.setSearchLoading(false);
        this.statusSection.classList.add('hidden');

        if (data.best) {
            this.results.best = data.best;
            this.bestApp.textContent = this.capitalize(data.best.app);
            this.bestPrice.textContent = `₹${data.best.price}`;
            this.bestAppBtn.textContent = this.capitalize(data.best.app);
            this.bestDeal.classList.remove('hidden');

            // Highlight best price card
            const bestCard = document.querySelector(`.price-card[data-app="${data.best.app}"]`);
            if (bestCard) {
                bestCard.classList.add('best-price');
            }
        }
    }

    setSearchLoading(loading) {
        if (loading) {
            this.btnText.classList.add('hidden');
            this.btnLoader.classList.remove('hidden');
            this.searchBtn.disabled = true;
        } else {
            this.btnText.classList.remove('hidden');
            this.btnLoader.classList.add('hidden');
            this.searchBtn.disabled = false;
        }
    }

    showStatus(title, message) {
        this.statusSection.classList.remove('hidden');
        this.statusTitle.textContent = title;
        this.statusMessage.textContent = message;
    }

    resetCards() {
        this.priceCards.forEach(card => {
            card.classList.remove('best-price');
            const loading = card.querySelector('.price-loading');
            const content = card.querySelector('.price-content');
            const productName = card.querySelector('.product-name');
            const badge = card.querySelector('.status-badge');
            const buyBtn = card.querySelector('.btn-buy');

            loading.classList.remove('hidden');
            content.classList.add('hidden');
            productName.textContent = 'Waiting...';
            badge.textContent = 'Pending';
            badge.className = 'status-badge pending';
            buyBtn.classList.add('hidden');
        });
    }

    setCardSearching(app) {
        const card = document.querySelector(`.price-card[data-app="${app}"]`);
        if (!card) return;

        const badge = card.querySelector('.status-badge');
        const productName = card.querySelector('.product-name');

        badge.textContent = 'Searching';
        badge.className = 'status-badge searching';
        productName.textContent = 'Searching...';
    }

    updateCard(app, result) {
        const card = document.querySelector(`.price-card[data-app="${app}"]`);
        if (!card) return;

        const loading = card.querySelector('.price-loading');
        const content = card.querySelector('.price-content');
        const priceValue = card.querySelector('.price-value');
        const productName = card.querySelector('.product-name');
        const badge = card.querySelector('.status-badge');
        const buyBtn = card.querySelector('.btn-buy');

        loading.classList.add('hidden');

        if (result.found && result.price) {
            content.classList.remove('hidden');
            priceValue.textContent = result.price;
            productName.textContent = this.currentProduct;
            badge.textContent = 'Found';
            badge.className = 'status-badge found';
            buyBtn.classList.remove('hidden');
        } else {
            content.classList.remove('hidden');
            priceValue.textContent = '--';
            productName.textContent = result.error || 'Not found';
            badge.textContent = 'Error';
            badge.className = 'status-badge error';
        }

        this.results[app] = result;
    }

    showOrderModal(app) {
        this.selectedOrderApp = app;
        this.orderApp.textContent = this.capitalize(app);
        this.orderProduct.textContent = this.currentProduct;
        this.orderModal.classList.remove('hidden');
    }

    hideOrderModal() {
        this.orderModal.classList.add('hidden');
    }

    async placeOrder() {
        this.hideOrderModal();

        // Show order status modal
        this.orderStatusModal.classList.remove('hidden');
        this.orderStatusTitle.textContent = '📦 Placing Order...';
        this.orderStatusMsg.textContent = `Automating order on ${this.capitalize(this.selectedOrderApp)}...`;

        try {
            const response = await fetch('/order', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    product: this.currentProduct,
                    app: this.selectedOrderApp
                })
            });

            const data = await response.json();

            // Connect to WebSocket for order updates
            const orderWs = new WebSocket(`ws://${window.location.host}/ws/${data.task_id}`);

            orderWs.onmessage = (event) => {
                const update = JSON.parse(event.data);

                if (update.status === 'completed') {
                    this.orderStatusTitle.textContent = '✅ Order Placed!';
                    this.orderStatusMsg.textContent = 'Your order has been placed successfully!';

                    setTimeout(() => {
                        this.orderStatusModal.classList.add('hidden');
                    }, 3000);

                    orderWs.close();
                } else if (update.status === 'error') {
                    this.orderStatusTitle.textContent = '❌ Order Failed';
                    this.orderStatusMsg.textContent = update.error || 'Failed to place order';

                    setTimeout(() => {
                        this.orderStatusModal.classList.add('hidden');
                    }, 3000);

                    orderWs.close();
                }
            };

        } catch (error) {
            console.error('Order error:', error);
            this.orderStatusTitle.textContent = '❌ Error';
            this.orderStatusMsg.textContent = 'Failed to communicate with server';

            setTimeout(() => {
                this.orderStatusModal.classList.add('hidden');
            }, 3000);
        }
    }

    capitalize(str) {
        return str.charAt(0).toUpperCase() + str.slice(1);
    }
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    window.priceHunter = new PriceHunter();
});
