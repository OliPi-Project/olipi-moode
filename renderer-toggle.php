<?php
/*
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2025 OliPi Project
 * Copyright 2014 The moOde audio player project / Tim Curtis
 */
require_once "/var/www/inc/common.php";
require_once "/var/www/inc/session.php";
require_once "/var/www/inc/renderer.php";

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

function toggle_renderer($name, $action) {

    phpSession('open');
    phpSession('load_system');

    switch ($name) {
        case 'bluetooth':
            if ($action === 'on') {
                $status = startBluetooth();
                if ($status === 'started') {
                    phpSession('write', 'btsvc', '1');
                    echo "✅ Bluetooth started\n";
                } else {
                    echo "❌ Bluetooth error: $status\n";
                }
            } else {
                stopBluetooth();
                phpSession('write', 'btsvc', '0');
                echo "⛔ Bluetooth stopped\n";
            }
            break;

        case 'airplay':
            if ($action === 'on') {
                startAirPlay();
                phpSession('write', 'airplaysvc', '1');
                echo "✅ AirPlay started\n";
            } else {
                stopAirPlay();
                phpSession('write', 'airplaysvc', '0');
                echo "⛔ AirPlay stopped\n";
            }
            break;

        case 'upnp':
            if ($action === 'on') {
                startUPnP();
                phpSession('write', 'upnpsvc', '1');
                echo "✅ UPnP started\n";
            } else {
                sysCmd('systemctl stop upmpdcli');
                phpSession('write', 'upnpsvc', '0');
                echo "⛔ UPnP stopped\n";
            }
            break;

        default:
            echo "Usage: php renderer-toggle.php [bluetooth|airplay|upnp] [on|off]\n";
            break;
    }

    phpSession('close');
}

// CLI entry
if ($argc != 3) {
    echo "Usage: php renderer-toggle.php [bluetooth|airplay|upnp] [on|off]\n";
    exit(1);
}

$name = strtolower($argv[1]);
$action = strtolower($argv[2]);
toggle_renderer($name, $action);
