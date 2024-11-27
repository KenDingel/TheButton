<?php
require_once 'config.php';

class GameDatabase {
    private $pdo;
    
    public function __construct() {
        $this->pdo = getDBConnection();
        if (!$this->pdo) throw new Exception("Database connection failed");
    }

    public function getActiveGames() {
        $stmt = $this->pdo->prepare("
            SELECT 
                gs.id, 
                gs.guild_id, 
                gs.timer_duration, 
                gs.cooldown_duration, 
                gs.start_time,
                gn.guild_name,
                (SELECT click_time 
                FROM button_clicks 
                WHERE game_id = gs.id 
                ORDER BY click_time DESC 
                LIMIT 1) as last_click
            FROM game_sessions gs
            LEFT JOIN guild_names gn ON gs.guild_id = gn.guild_id
            WHERE gs.end_time IS NULL
            ORDER BY gs.id DESC
        ");
        $stmt->execute();
        $games = $stmt->fetchAll(PDO::FETCH_ASSOC);

        // Fetch stats for each game
        foreach ($games as &$game) {
            $game['stats'] = $this->getGameStats($game['id']);
        }

        return $games;
    }



    public function getRecentClicks($limit) {
        $stmt = $this->pdo->prepare("
            SELECT 
                bc.timer_value,
                bc.click_time,
                u.user_name,
                gs.guild_id,
                gs.id as game_id,
                gs.timer_duration,
                gn.guild_name
            FROM button_clicks bc
            JOIN users u ON bc.user_id = u.user_id
            JOIN game_sessions gs ON bc.game_id = gs.id
            LEFT JOIN guild_names gn ON gs.guild_id = gn.guild_id
            ORDER BY bc.click_time DESC
            LIMIT :limit
        ");
        $stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
        $stmt->execute();
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    public function getLowestClicks($limit) {
        $stmt = $this->pdo->prepare("
            SELECT 
                bc.timer_value,
                bc.click_time,
                u.user_name,
                gs.guild_id,
                gs.id as game_id,
                gs.timer_duration,
                gn.guild_name
            FROM button_clicks bc
            JOIN users u ON bc.user_id = u.user_id
            JOIN game_sessions gs ON bc.game_id = gs.id
            LEFT JOIN guild_names gn ON gs.guild_id = gn.guild_id
            ORDER BY bc.timer_value ASC
            LIMIT :limit
        ");
        $stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
        $stmt->execute();
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    public function getGameLeaderboard($gameId) {
        $stmt = $this->pdo->prepare("
            SELECT 
                u.user_name,
                COUNT(*) as total_clicks,
                MIN(bc.timer_value) as lowest_time,
                MAX(bc.click_time) as last_click,
                SUM(gs.timer_duration - bc.timer_value) as time_saved
            FROM button_clicks bc
            JOIN users u ON bc.user_id = u.user_id
            JOIN game_sessions gs ON bc.game_id = gs.id
            WHERE bc.game_id = :game_id
            GROUP BY u.user_id, u.user_name
            ORDER BY total_clicks DESC
            LIMIT 10
        ");
        $stmt->bindValue(':game_id', $gameId, PDO::PARAM_INT);
        $stmt->execute();
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    public function getGameStats($gameId) {
        // Get basic stats
        $stmt = $this->pdo->prepare("
            SELECT 
                MIN(timer_value) as time_to_beat,
                COUNT(DISTINCT user_id) as total_players,
                COUNT(*) as total_clicks,
                TIMESTAMPDIFF(SECOND, MIN(click_time), MAX(click_time)) as button_alive_time
            FROM button_clicks
            WHERE game_id = :game_id
        ");
        $stmt->bindValue(':game_id', $gameId, PDO::PARAM_INT);
        $stmt->execute();
        $basicStats = $stmt->fetch(PDO::FETCH_ASSOC);

        // Get record holder (user with the lowest timer_value)
        $stmt = $this->pdo->prepare("
            SELECT u.user_name
            FROM button_clicks bc
            JOIN users u ON bc.user_id = u.user_id
            WHERE bc.game_id = :game_id
            ORDER BY bc.timer_value ASC, bc.click_time ASC
            LIMIT 1
        ");
        $stmt->bindValue(':game_id', $gameId, PDO::PARAM_INT);
        $stmt->execute();
        $recordHolder = $stmt->fetchColumn();

        // Get top time claimer (user who claimed the most time)
        $stmt = $this->pdo->prepare("
            SELECT u.user_name, SUM(gs.timer_duration - bc.timer_value) as time_claimed
            FROM button_clicks bc
            JOIN game_sessions gs ON bc.game_id = gs.id
            JOIN users u ON bc.user_id = u.user_id
            WHERE bc.game_id = :game_id
            GROUP BY bc.user_id
            ORDER BY time_claimed DESC
            LIMIT 1
        ");
        $stmt->bindValue(':game_id', $gameId, PDO::PARAM_INT);
        $stmt->execute();
        $topClaimerData = $stmt->fetch(PDO::FETCH_ASSOC);

        // Assemble the stats array
        $stats = [
            'time_to_beat' => $basicStats['time_to_beat'],
            'total_players' => $basicStats['total_players'],
            'total_clicks' => $basicStats['total_clicks'],
            'button_alive_time' => $basicStats['button_alive_time'],
            'record_holder' => $recordHolder ?: 'No record yet',
            'top_time_claimer' => $topClaimerData['user_name'] ?? 'No claims yet',
            'top_claimed_time' => $topClaimerData['time_claimed'] ?? 0,
        ];

        return $stats;
    }


public function getRecentColorPattern($gameId) {
    $stmt = $this->pdo->prepare("
        SELECT 
            bc.timer_value,
            gs.timer_duration
        FROM button_clicks bc
        JOIN game_sessions gs ON bc.game_id = gs.id
        WHERE bc.game_id = :game_id
        ORDER BY bc.click_time DESC
        LIMIT 10
    ");
    $stmt->bindValue(':game_id', $gameId, PDO::PARAM_INT);
    $stmt->execute();
    return $stmt->fetchAll(PDO::FETCH_ASSOC);
}

public function getActivityStats($gameId) {
    try {
        $stmt = $this->pdo->prepare("
            SELECT 
                HOUR(click_time) as hour,
                COUNT(*) as click_count
            FROM button_clicks
            WHERE game_id = :game_id
            GROUP BY HOUR(click_time)
            ORDER BY HOUR(click_time)
        ");
        $stmt->bindValue(':game_id', $gameId, PDO::PARAM_INT);
        $stmt->execute();
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    } catch (PDOException $e) {
        throw new Exception("Failed to fetch activity stats: " . $e->getMessage());
    }
}
}
?>