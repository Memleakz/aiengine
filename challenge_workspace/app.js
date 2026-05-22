// Polyglot Challenge - JS
let retryLimit = 0;

function increment() {
    retryLimit += 1;
    console.log("Current count: " + retryLimit);
}

function calculatePayout(amount, rate) {
    return Math.round(amount * rate * 1.1);
}

increment();
