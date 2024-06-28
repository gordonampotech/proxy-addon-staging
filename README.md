# Proxy Server for Home Assistant

## Why the need for a Proxy Server

Each Home Assistant Hub in a home is a server by itself and only can be accessed by:

1. **Port Forwarding to the port running Home Assistant**\
   Port forwarding is free but some households may not be able to port forward due to their ISPs putting them behind a CGNAT

2. **Using a Tunneling service (Cloudflare Tunnels)**\
   Tunneling for small number of Home Assistant instances is free but is difficult to manage. Plus, once the numbers scale up, it is not feasible anymore.

3. **Home Assistant Cloud (Nabu Casa)**\
   Home Assistant Cloud is a paid service ($6 per month per Home Assistant Hub).

Due to these reason, we are creating our own Home Assistant Proxy Server which will allow external access to customer's Home Assistant Hubs without needing to port forward at a much lower cost per Hub.

## Overall Flow

**During set-up of a customer Hubs, they each will be assigned a subdomain and a unique identifying token. The subdomain and tokens will both be used to establish connections.**

**Note that our Proxy Client is running on each customer's Home Assistant Hub as a Home Assistant Addon.**

```
         <--------------->         Socket.io                    <------------->
External <-- WSS/HTTPS --> Server <---------> Client (HA Addon) <-- WS/HTTP --> HA Instance
         <--------------->                                      <------------->
```

### HTTP Request Flow

1. Each `Client` connects to the `Server` via a Socket.io connection, sending over its subdomain and token for verification during the handshake. If the subdomain and token is valid, the connection is established.

2. External Devices makes HTTP requests to the `Server` domain name (currently `ampo-demo.online`). The requests need to have a subdomain attached (e.g. `abc.ampo-demo.online`). This subdomain is the identifier as to which Home Assistant (HA) Instance the HTTP request is meant for.

3. The `Server` maintains a map of each of the connected `Clients` and their respective subdomain, it checks against this map when a HTTP request comes in. If valid, the `Server` forwards this request to the `Client` via the Socket.io connection and waits for a reply from the `Client`.

4. After receiving the request, the `Client` uses the incoming data to send another request to the `HA Instance` locally (both the `HA instance` and `Client` are docker containers running on the Home Assistant Hub).

5. The `HA Instance` responds to the `Client`.

6. The `Client` sends the response back to the `Server` with the response status, header and body.

7. The `Server` receives the response and finally replies the External Device that made the request.

### Websocket Flow

1. (Same as HTTP) Each `Client` connects to the `Server` via a Socket.io connection, sending over its subdomain and token for verification during the handshake. If the subdomain and token is valid, the connection is established.

2. External Devices makes **HTTP upgrade** requests to the `Server` domain name (currently `ampo-demo.online`) to establish a websocket connection. The requests need to have a subdomain attached (e.g. `abc.ampo-demo.online`). This subdomain is the identifier as to which HA Instance the websocket messages are meant for.

3. The `Server` maintains a map of each of the connected `Clients` and their respective subdomain in the `sockio_connections` map. It checks against this map when a HTTP upgrade request comes in.

4. If there exists a connection, the `Server` establishes a websocket connection with the External Device and assigns it an **internal UUID** and stores it in a UUID-to-External Websocket map called `uws_connections`.

5. The `Server` then notifies the correct `Client` via the Socket.io connection that there has been a new external websocket connection and at the same time, sends over the UUID of the websocket.

6. The `Client` then establishes its own Websocket connection to the `HA Instance` and maps the UUID from the `Server` to the newly established HA Websocket session in the `self.sessions` property.

7. An `asyncio` task is then started to continuously listen for messages from the `HA Instance`.

8. When a Websocket message is sent from via the External Websocket to the `Server`, the message is forwarded to the respective `Client` together with the UUID of the External Websocket. `Server` does NOT wait for replies from the `Client`.

9. The `Client` uses its internal UUID-to-HA Websocket mapping and forwards it to correct HA Websocket.

10. Whenever, there is a response on one of the Websockets from the `HA Instance`, the `Client` forwards the response to the `Server` with the UUID attached.

11. The `Server` uses its internal UUID-to-External Websocket mapping to send the received message back to the correct External Device.

12. External Websocket disconnections are handled similarly to connections.

## NGINX

Current implementation uses a NGINX server to handle TLS termination. The SSL Cert is a wildcard Cert that is generated using LetsEncrypt and [Certbot](https://certbot.eff.org/instructions). It also passes the subdomain of incoming requests as a header so that it can be easily accessed by our `Server`.

The NGINX server redirects any regular HTTP access to `ampo-demo.online` to the HTTPS port. HTTPS traffic is then proxied to the `Server` using the 3 `location` blocks for Websocket, Socketio and all other requests.

nginx.conf (snippet)

```
server {
    listen 80;
        server_name ampo-demo.online *.ampo-demo.online;

        return 301 https://$host$request_uri;
}

server {
    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/ampo-demo.online/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/ampo-demo.online/privkey.pem; # managed by Certbot
    include /etc/letsencrypt/options-ssl-nginx.conf; # managed by Certbot
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; # managed by Certbot

    server_name ampo-demo.online ~^(?<subdomain>.+)\.ampo-demo.online;
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;

    # This is for external websocket connections
    location /api/websocket {
        proxy_pass http://localhost:7359;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header X-Subdomain $subdomain;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
    location /socket.io/ {
        proxy_pass http://localhost:7359/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
    location / {
        proxy_pass http://localhost:7359;
        proxy_http_version 1.1;
        proxy_set_header X-Subdomain $subdomain;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}

```

## To Developers

To update the version of the addon

Change the version in ./proxy-addon-staging/config.yaml, e.g. version: "1.0.2" -> version: "1.2.0"

After that, build the new docker image and push to the docker registry
```
docker build -t ghcr.io/gordonampotech/proxy-addon-staging:<version_number> --platform linux/aarch64 .
docker push ghcr.io/gordonampotech/proxy-addon-staging:<version_number>
```

The update will show up automatically in home assistant, but will take a bit of time even after manually clicking check for update.