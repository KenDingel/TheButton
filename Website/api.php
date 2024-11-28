<?php
require_once 'config.php';
require_once 'database.php';

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
header('Cache-Control: post-check=0, pre-check=0', false);
header('Pragma: no-cache');
header('Expires: Sat, 26 Jul 1997 05:00:00 GMT'); // Past date to ensure no caching

try {
    $db = new GameDatabase();
    $action = $_GET['action'] ?? '';
    $gameId = isset($_GET['gameId']) ? filter_var($_GET['gameId'], FILTER_VALIDATE_INT) : null;
    
    $response = ['success' => false, 'data' => null, 'error' => null];
    
    switch ($action) {
        case 'getActiveGames':
            $response['data'] = $db->getActiveGames();
            $response['success'] = true;
            break;
            
        case 'getGameLeaderboard':
            if (!$gameId) throw new Exception('Game ID required');
            $response['data'] = $db->getGameLeaderboard($gameId);
            $response['success'] = true;
            break;
            
        case 'getRecentClicks':
            $limit = isset($_GET['limit']) ? min(100, max(1, intval($_GET['limit']))) : 25;
            $response['data'] = $db->getRecentClicks($limit);
            $response['success'] = true;
            break;
            
        case 'getLowestClicks':
            $limit = isset($_GET['limit']) ? min(100, max(1, intval($_GET['limit']))) : 25;
            $response['data'] = $db->getLowestClicks($limit);
            $response['success'] = true;
            break;

        case 'getActivityStats':
            if (!$gameId) {
                throw new Exception('Game ID required');
            }
            $response['data'] = $db->getActivityStats($gameId);
            $response['success'] = true;
            break;
            
        default:
            throw new Exception('Invalid action');
    }
    $response['timestamp'] = gmdate('Y-m-d\TH:i:s\Z');
    echo json_encode($response);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        'success' => false,
        'error' => $e->getMessage(),
        'timestamp' => gmdate('Y-m-d\TH:i:s\Z')
    ]);
}
?>