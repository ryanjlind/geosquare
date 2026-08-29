import { initGame } from './game.js?v=4';

window.addEventListener('error', event => {
	console.error('Uncaught JavaScript error:', event.error || event.message);
});

window.addEventListener('unhandledrejection', event => {
	console.error('Unhandled promise rejection:', event.reason);
});

initGame();