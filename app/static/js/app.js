import { initGame } from '@geosquare/game.js';

window.addEventListener('error', event => {
	console.error('Uncaught JavaScript error:', event.error || event.message);
});

window.addEventListener('unhandledrejection', event => {
	console.error('Unhandled promise rejection:', event.reason);
});

initGame();