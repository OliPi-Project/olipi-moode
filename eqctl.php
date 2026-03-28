#!/usr/bin/env php
<?php
/*
 * SPDX-License-Identifier: GPL-3.0-or-later
 * CLI helper for moOde EQ control
 */

require_once '/var/www/inc/common.php';
require_once '/var/www/inc/alsa.php';
require_once '/var/www/inc/audio.php';
require_once '/var/www/inc/eqp.php';
require_once '/var/www/inc/session.php';
require_once '/var/www/inc/sql.php';

error_reporting(E_ALL);
ini_set('display_errors', 1);


// --- Session ---
$sessionId = phpSession('get_sessionid');
if (!$sessionId) {
    echo "No active session ID found in cfg_system.\n";
    exit(1);
}
session_id($sessionId);
phpSession('open');
phpSession('load_system');

$dbh = sqlConnect();

function out($msg = '') {
    echo $msg . PHP_EOL;
}

function usage() {
    out("Usage:");
    out("  eqctl eqp12 list|status|set <id|name|off>");
    out("  eqctl alsaequal list|status|set <id|name|off>");
    exit(1);
}

function normalize_arg($s) {
    return trim((string)$s);
}

// --- EQP12 (Parametric EQ) ---
function resolve_eqp12_target($dbh, $arg) {
    $eqp12 = Eqp12($dbh);
    $presets = $eqp12->getPresets();

    $arg = normalize_arg($arg);
    if ($arg === '' || strtolower($arg) === 'off' || $arg === '0') return 0;
    if (ctype_digit($arg)) {
        $id = intval($arg);
        return array_key_exists($id, $presets) ? $id : null;
    }
    foreach ($presets as $id => $name) {
        if (strcasecmp($name, $arg) === 0) return intval($id);
    }
    return null;
}

function set_eqp12($dbh, $target) {
    $eqp12 = Eqp12($dbh);
    $old = $eqp12->getActivePresetIndex();
    $new = $target;

    if ($new === null) {
        out("ERR: unknown eqp12 preset");
        exit(2);
    }

    // --- Protections ---
    if ($new != 0 && ($_SESSION['alsaequal'] ?? 'Off') !== 'Off') {
        out("Graphic EQ must be off before activating Parametric EQ preset");
        exit(3);
    }
    if ($new != 0 && ($_SESSION['peppy_display'] ?? '0') === '1' && ($_SESSION['alsa_output_mode'] ?? '') === 'plughw') {
        out('When Peppy is on, ALSA output mode cannot be "Default".');
        exit(4);
    }

    if ($new == $old) {
        out("OK eqp12 unchanged ($old)");
        return;
    }

    $eqp12->setActivePresetIndex($new);
    phpSession('write', 'eqfa12p', $new == 0 ? 'Off' : 'On');
    submitJob('eqfa12p', $old . ',' . $new);
    out("OK eqp12 $old -> $new");
}

function list_eqp12($dbh) {
    $eqp12 = Eqp12($dbh);
    $presets = $eqp12->getPresets();
    $active = $eqp12->getActivePresetIndex();
    out("0|Off|" . ($active == 0 ? "1" : "0"));
    foreach ($presets as $id => $name) {
        out($id . "|" . $name . "|" . ($active == $id ? "1" : "0"));
    }
}

function status_eqp12($dbh) {
    $eqp12 = Eqp12($dbh);
    $active = $eqp12->getActivePresetIndex();
    $presets = $eqp12->getPresets();
    $name = $active === 0 ? 'Off' : ($presets[$active] ?? 'Unknown');
    out("eqp12|$active|$name");
}

// --- ALSA Graphic EQ ---
function resolve_alsaequal_target($dbh, $arg) {
    $arg = normalize_arg($arg);

    if ($arg === '' || strtolower($arg) === 'off' || $arg === '0') {
        return 'Off';
    }

    $rows = sqlQuery("SELECT id, curve_name FROM cfg_eqalsa ORDER BY id", $dbh);

    // --- ID lookup ---
    if (ctype_digit($arg)) {
        $id = intval($arg);
        foreach ($rows as $row) {
            if (intval($row['id']) === $id) {
                return $row['curve_name'];
            }
        }
        return null;
    }

    // --- Name lookup ---
    foreach ($rows as $row) {
        if (strcasecmp($row['curve_name'], $arg) === 0) {
            return $row['curve_name'];
        }
    }

    return null;
}

function set_alsaequal($dbh, $target) {
    $old = $_SESSION['alsaequal'] ?? 'Off';
    $new = $target;

    if ($new === null) {
        out("ERR: unknown alsaequal curve");
        exit(2);
    }

    // --- Protections ---
    if ($new !== 'Off' && ($_SESSION['eqfa12p'] ?? 'Off') !== 'Off') {
        out("Parametric EQ must be off before activating Graphic EQ preset");
        exit(3);
    }
    if ($new !== 'Off' && ($_SESSION['peppy_display'] ?? '0') === '1' && ($_SESSION['alsa_output_mode'] ?? '') === 'plughw') {
        out('When Peppy is on, ALSA output mode cannot be "Default".');
        exit(4);
    }

    if ($new === $old) {
        out("OK alsaequal unchanged ($old)");
        return;
    }

    phpSession('write', 'alsaequal', $new);
    submitJob('alsaequal', $old . ',' . $new);
    out("OK alsaequal $old -> $new");
}

function list_alsaequal($dbh) {
    $rows = sqlQuery("SELECT id, curve_name FROM cfg_eqalsa ORDER BY id", $dbh);
    $active = $_SESSION['alsaequal'] ?? 'Off';
    out("0|Off|" . ($active === 'Off' ? "1" : "0"));
    foreach ($rows as $row) {
        out($row['id'] . "|" . $row['curve_name'] . "|" . ($active === $row['curve_name'] ? "1" : "0"));
    }
}

function status_alsaequal($dbh) {
    $active = $_SESSION['alsaequal'] ?? 'Off';
    out("alsaequal|" . $active);
}

// --- CLI dispatch ---
$mode = $argv[1] ?? '';
$cmd  = $argv[2] ?? '';
$arg  = $argv[3] ?? '';

if ($mode === '' || $cmd === '') usage();

if ($mode === 'eqp12') {
    if ($cmd === 'list') list_eqp12($dbh);
    elseif ($cmd === 'status') status_eqp12($dbh);
    elseif ($cmd === 'set') set_eqp12($dbh, resolve_eqp12_target($dbh, $arg));
    else usage();
} elseif ($mode === 'alsaequal') {
    if ($cmd === 'list') list_alsaequal($dbh);
    elseif ($cmd === 'status') status_alsaequal($dbh);
    elseif ($cmd === 'set') set_alsaequal($dbh, resolve_alsaequal_target($dbh, $arg));
    else usage();
} else usage();

phpSession('close');
