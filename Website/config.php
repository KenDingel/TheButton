<?php
// config.php - Database configuration and constants
define('DB_HOST', 'moonstorage.moondev.dreamhosters.com');
define('DB_NAME', 'thebutton');
define('DB_USER', 'stinky_admin');
define('DB_PASS', 'Disagree5-Goon-Anyplace');
define('DB_PORT', 3306);

// Color constants matching Python thresholds
define('COLOR_THRESHOLDS', [
    ['name' => 'Purple', 'threshold' => 83.33, 'rgb' => '6A4C93'],
    ['name' => 'Blue', 'threshold' => 66.67, 'rgb' => '4069C0'],
    ['name' => 'Green', 'threshold' => 50.00, 'rgb' => '509B69'],
    ['name' => 'Yellow', 'threshold' => 33.33, 'rgb' => 'CBA635'],
    ['name' => 'Orange', 'threshold' => 16.67, 'rgb' => 'DB7C30'],
    ['name' => 'Red', 'threshold' => 0, 'rgb' => 'C24141']
]);

// Initialize PDO connection with error handling
function getDBConnection() {
    try {
        $dsn = "mysql:host=" . DB_HOST . ";dbname=" . DB_NAME . ";port=" . DB_PORT;
        $pdo = new PDO($dsn, DB_USER, DB_PASS);
        $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        $pdo->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
        return $pdo;
    } catch (PDOException $e) {
        error_log("Database connection failed: " . $e->getMessage());
        return null;
    }
}

// Security headers
header("Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' cdn.tailwindcss.com; style-src 'self' 'unsafe-inline' cdn.tailwindcss.com; img-src 'self' data:;");
header("X-Content-Type-Options: nosniff");
header("X-Frame-Options: DENY");
header("X-XSS-Protection: 1; mode=block");
header("Referrer-Policy: no-referrer");
?>