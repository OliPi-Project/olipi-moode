<?php
/*
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2025 OliPi Project / Benoit Toufflet
 * Copyright 2014 The moOde audio player project / Tim Curtis
 */
require_once "/var/www/inc/common.php";
require_once "/var/www/inc/session.php";

$stationUrl = $argv[1];
$stationName = $argv[2];
$type = $argv[3];
$bitrate = $argv[4];
$format = $argv[5];

// 1. Get session ID
$sessionId = phpSession('get_sessionid');
if (!$sessionId) {
    echo "❌ No active session ID found.\n";
    exit(1);
}
session_id($sessionId);
if (session_start() === false) {
    echo "❌ Session start failed.\n";
    exit(1);
}

// 2. Update session
phpSession('open');
$_SESSION[$stationUrl] = array(
    'name' => $stationName,
    'type' => $type,
    'logo' => 'local',
    'bitrate' => $bitrate,
    'format' => $format,
    'home_page' => '',
    'monitor' => 'No'
);
phpSession('close');

echo "✅ Session updated for $stationName\n";
?>
