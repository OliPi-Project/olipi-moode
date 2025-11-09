<?php
/*
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2025 OliPi Project
 * Copyright 2014 The moOde audio player project / Tim Curtis
 */
require_once "/var/www/inc/common.php";
require_once "/var/www/inc/alsa.php";
require_once "/var/www/inc/audio.php";
require_once "/var/www/inc/mpd.php";
require_once "/var/www/inc/session.php";

$sessionId = phpSession('get_sessionid');
if (!$sessionId) {
    echo "❌ No active session ID found in cfg_system.\n";
    exit(1);
}
session_id($sessionId);
if (session_start() === false) {
    echo "❌ Session start failed.\n";
    exit(1);
}
phpSession('open');
phpSession('load_system');

if ($argc < 2) {
    echo "[AUDIOOUT_USAGE]\n";
    exit(1);
}

$audioout = $argv[1];
if (!in_array($audioout, ['Local', 'Bluetooth'])) {
    echo "[AUDIOOUT_INVALID]\n";
    exit(1);
}


$currentAudioOut = $_SESSION['audioout'] ?? 'Local';

if ($audioout === $currentAudioOut) {
    echo "[AUDIOOUT_ALREADY_SET] $audioout\n";
    phpSession('close');
    exit(0);
}

if ($audioout === 'Bluetooth') {
    $result = sysCmd('/var/www/util/blu-control.sh -c');
    $connectedMac = null;
    foreach ($result as $line) {
        if (preg_match('/^\*\*\s*([0-9A-F:]{17})\s*(.*)$/i', $line, $matches)) {
            $connectedMac = $matches[1];
            break;
        }
    }
    if (!$connectedMac) {
        echo "[AUDIOOUT_NO_BT]\n";
        phpSession('close');
        exit(1);
    }
    sysCmd("sed -i '/device/c\\device \"$connectedMac\"' " . ALSA_PLUGIN_PATH . "/btstream.conf");
    sysCmd("/var/www/util/blu-control.sh -C \"$connectedMac\"");
    sleep(1);
}

if ($audioout === 'Local' && $currentAudioOut === 'Bluetooth') {
    $result = sysCmd('/var/www/util/blu-control.sh -c');
    $connectedMac = null;
    foreach ($result as $line) {
        if (preg_match('/^\*\*\s*([0-9A-F:]{17})\s*(.*)$/i', $line, $matches)) {
            $connectedMac = $matches[1];
            break;
        }
    }
    if ($connectedMac) {
        sysCmd("/var/www/util/blu-control.sh -d \"$connectedMac\"");
        sleep(1);
    }
}

phpSession('write', 'audioout', $audioout);
setAudioOut($audioout);

phpSession('close');

echo "[AUDIOOUT_CHANGED] $audioout\n";
