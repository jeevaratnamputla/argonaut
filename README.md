# slack chatgpt bot  
pre-requisites  
1. slack app set up ( see slack.md)  
2. elasticsearch install ( helm install elasticsearch)  
3. external secrets install (helm install external secrets, create secret with aws account access and seret key (that can read secrets) create cluster secret store)  
4. secrets for slack token, openAI APi token, slack signing secret, argocd url, username, password secret, github token secret  
5. get the username for the slack bot and put it in main.py.  
  
installation  
in same namespace as elasticsearch  
clone this repo  
kubectl -n <namespace> apply -k .  
