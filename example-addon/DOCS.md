# Home Assistant Proxy Client Addon

## Overview

This addon enables your Home Assistant Hub to connect securely to an external proxy server, allowing remote access without the need for port forwarding or a VPN. It's designed for homes behind CGNAT or those who prefer not to expose Home Assistant directly to the internet.

### Key Features

- Secure remote access to your Home Assistant instance.
- Easy setup with automatic subdomain and token assignment.

## Prerequisites

- Home Assistant Core installation.
- Basic understanding of Home Assistant Addons.

## Installation

### Step 1: Add Repository

1. Navigate to **Supervisor > Add-on Store** in your Home Assistant UI.
2. Click on the **Repositories** button in the top right corner.
3. Enter the URL of the addon repository and click **Add**.

### Step 2: Install Addon

1. Scroll down to find the **Home Assistant Proxy Client** addon in the list.
2. Click on it and then click **Install**.


## Usage

### Starting the Addon

- After saving your configuration, start the addon by clicking **Start**.
- Enable **Start on boot** if you want the addon to automatically start with Home Assistant.

### Verifying the Connection

- Once started, you can verify the connection status in the addon logs.
- Look for messages indicating a successful connection to the proxy server.

## Troubleshooting

If you encounter issues, please check the following:

- Verify your internet connection.
- Restart the addon and check the logs for error messages.
- For detailed troubleshooting, refer to [our troubleshooting guide](#).

