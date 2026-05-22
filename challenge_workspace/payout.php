<?php
// Polyglot Challenge - PHP
class PayoutCalculator {
    private $baseRate;

    public function __construct($baseRate) {
        $this->baseRate = $baseRate;
    }

    public function getPayment($hours) {
        return $hours * $this->baseRate;
    }
}

$calc = new PayoutCalculator(25.0);
echo $calc->getPayment(40);
