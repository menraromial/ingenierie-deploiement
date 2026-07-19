# Chapitre 7 : Réseau privé entre machines

!!! abstract "Objectifs du chapitre"
    À l'issue de ce chapitre, vous saurez :

    - choisir le bon mode réseau VirtualBox pour chaque besoin (NAT, host-only, interne, pont) et expliquer ce que chacun simule du monde réel ;
    - concevoir et documenter un plan d'adressage privé ;
    - configurer une interface statique sur Ubuntu avec netplan ;
    - organiser la résolution de noms interne d'un petit parc, et en connaître les limites.

    C'est le chapitre d'outillage du [TP 5](../tp/tp5-eclater-application.md) : tout ce qui s'y câble se décide ici.

## 1. Le besoin : un réseau qui n'appartient qu'au système

L'architecture du chapitre 6 suppose un lien entre nos machines que l'extérieur ne voit pas : le trafic backend→base ne doit ni sortir sur Internet, ni être joignable depuis le poste d'un autre étudiant. Ce besoin est universel et porte des noms différents selon l'échelle :

| Contexte | Le « réseau privé » s'appelle | Exemple |
|---|---|---|
| Datacenter physique | VLAN, réseau de management | Le lien dédié entre serveurs d'applications et baie de stockage |
| Cloud public | **VPC** (*Virtual Private Cloud*), sous-réseaux privés | Un sous-réseau « données » sans route vers Internet |
| Nos TP | Réseau **host-only** VirtualBox | `192.168.56.0/24`, partagé entre l'hôte et les VM |

Le TP reproduit donc fidèlement, à l'échelle du poste, la topologie « un sous-réseau privé + une passerelle d'accès » que vous retrouverez dans tout VPC. C'est le sens de la philosophie « tout en local » : les concepts sont identiques, seul le fournisseur du réseau change.

## 2. Les modes réseau de VirtualBox

VirtualBox attache jusqu'à 4 cartes réseau virtuelles par VM, chacune dans un mode. Les connaître, c'est savoir *quoi* simuler :

| Mode | La VM voit Internet ? | L'hôte joint la VM ? | Les VM se joignent ? | Simule quoi ? |
|---|---|---|---|---|
| **NAT** (défaut) | Oui | Non (sauf redirections de ports) | **Non** | Un poste client derrière une box |
| **NAT Network** | Oui | Non (sauf redirections) | Oui | Un LAN derrière un routeur commun |
| **Host-only** | **Non** | **Oui** | **Oui** | Un réseau interne + lien d'administration |
| **Interne** (*internal*) | Non | **Non** | Oui | Un réseau strictement inter-serveurs |
| **Pont** (*bridged*) | Oui | Oui | Oui | La VM branchée directement sur le réseau physique |

Notre choix pour le bloc, et sa justification :

- **Carte 1 : NAT** sur chaque VM, inchangée depuis le TP 1 : elle fournit Internet (APT) et rien d'autre. Les VM n'y sont pas joignables, c'est très bien ainsi.
- **Carte 2 : host-only** : le réseau privé du système, *et* le chemin d'administration depuis l'hôte. Fini les redirections de ports : vous ferez `ssh deploy@192.168.56.11` directement, et le navigateur atteindra `https://listify.local` sans numéro de port exotique. La friction du NAT (TP 1 et 3) prend fin, et vous savez désormais exactement ce qu'elle valait.

!!! note "Pourquoi pas le mode interne, plus « pur » ?"
    Le mode interne isolerait aussi les VM de l'hôte : plus de SSH direct, plus de navigateur, retour aux redirections de ports pour chaque machine. Le host-only est le compromis pédagogique standard : réseau privé pour le système, accessible à l'administrateur (vous). En production, ce double rôle existe aussi : on parle de **réseau de management**. Le mode pont, lui, est interdit en salle de TP : il exposerait vos VM, à peine durcies, à tout le réseau de l'école.

## 3. Le plan d'adressage

### 3.1 Choisir le sous-réseau

Le réseau host-only par défaut de VirtualBox est `192.168.56.0/24` : une plage privée (RFC 1918, ch. 3) de 254 adresses utilisables, largement assez. Rappel appliqué du `/24` : les 24 premiers bits (192.168.56) identifient le réseau, le dernier octet identifie la machine ; toutes nos adresses seront donc `192.168.56.x` avec un masque `255.255.255.0`.

### 3.2 Attribuer : la convention avant les adresses

Un plan d'adressage n'est pas une liste, c'est une **convention** qui rend les adresses prévisibles. La nôtre, à respecter en TP :

| Plage | Usage | Attributions |
|---|---|---|
| `.1` | L'hôte (fixé par VirtualBox) | `192.168.56.1` |
| `.2` à `.9` | Réservé (DHCP VirtualBox si activé, équipements futurs) | : |
| `.10` à `.19` | Tier exposé | `.10` = listify-lb |
| `.20` à `.29` | Tier applicatif | `.21` = listify-app1, `.22` = listify-app2 |
| `.30` à `.39` | Tier données | `.31` = listify-db |

Le numéro **encode la zone** : croiser `192.168.56.22` dans un journal vous dit immédiatement « un backend ». Ce réflexe de conception paraît superflu à 4 machines ; à 40, il sépare les équipes qui s'y retrouvent de celles qui grep au hasard. Dans les organisations, ce travail a un nom et des outils : l'**IPAM** (*IP Address Management*) ; à notre échelle, un tableau dans le README du dépôt suffit, et il est **exigé** dans les livrables du TP 5.

!!! warning "Désactivez le DHCP du réseau host-only"
    VirtualBox propose un serveur DHCP sur vboxnet0. Nous le **désactivons** (TP 5, étape 0) : des serveurs doivent avoir des adresses **statiques et connues**, pas des baux qui changent au gré des redémarrages ; et un DHCP concurrent de vos adresses statiques produit des conflits difficiles à diagnostiquer.

## 4. Configurer l'interface sur Ubuntu : netplan

### 4.1 Les interfaces et leurs noms

Dans la VM, chaque carte VirtualBox apparaît comme une interface : la carte 1 (NAT) est `enp0s3`, la carte 2 (host-only) sera `enp0s8`. Ces noms « prévisibles » encodent la position sur le bus PCI (*en* = Ethernet, *p0s8* = bus 0, slot 8) : ils ont remplacé les `eth0/eth1` historiques précisément parce que l'ordre de détection de ces derniers pouvait changer d'un boot à l'autre. Vérification systématique avant toute configuration :

```bash
ip -brief link      # la liste des interfaces et leur état
ip -brief addr      # ... et leurs adresses
```

### 4.2 netplan : la configuration réseau déclarée

Ubuntu configure son réseau via **netplan** : des fichiers YAML dans `/etc/netplan/`, qu'un `netplan apply` traduit pour le démon de réseau (systemd-networkd sur Ubuntu Server). C'est notre premier vrai contact avec un outil **déclaratif** : le fichier décrit l'état voulu (« enp0s8 porte 192.168.56.21/24 »), pas la suite de commandes pour y parvenir. Retenez la sensation, le bloc 3 en fera un principe.

```yaml title="/etc/netplan/60-hostonly.yaml (exemple pour listify-app1)"
network:
  version: 2
  ethernets:
    enp0s8:
      addresses:
        - 192.168.56.21/24
```

```bash
sudo chmod 600 /etc/netplan/60-hostonly.yaml   # netplan exige des permissions strictes
sudo netplan try      # applique, et REVIENT EN ARRIÈRE en 120 s sans confirmation
ip -brief addr        # vérifier : enp0s8 porte bien l'adresse
```

Trois détails qui comptent :

- **Pas de `gateway`** dans ce fichier : la route par défaut (Internet) passe par la carte NAT `enp0s3`, gérée par le fichier netplan d'origine (`50-cloud-init.yaml`, encore lui). Le réseau host-only n'a pas de sortie, et c'est voulu.
- **`netplan try` plutôt que `apply`** quand on travaille en SSH : une erreur de configuration réseau, c'est la connexion coupée ; `try` annule tout seul si vous ne confirmez pas. Le cousin réseau du « gardez une session SSH ouverte » du TP 1.
- **Le YAML est indenté à l'espace, jamais à la tabulation**, et l'indentation *est* la syntaxe. Première rencontre avec le format qui portera Ansible, Kubernetes et Compose : autant prendre tout de suite l'habitude de la rigueur.

## 5. La résolution de noms interne

### 5.1 /etc/hosts distribué : la solution du bloc

Nos services doivent se désigner par des **noms**, pas des adresses : `DB_HOST=listify-db` survivra à un changement d'adresse, `DB_HOST=192.168.56.31` non (et le facteur III du ch. 4 vous dit déjà où ce nom doit vivre : dans la configuration). À 4 machines, la solution standard est le fichier `/etc/hosts` **identique sur toutes les machines** (et sur l'hôte pour les noms que vous utilisez depuis le navigateur) :

```text title="Bloc à ajouter au /etc/hosts de CHAQUE VM"
192.168.56.10   listify-lb
192.168.56.21   listify-app1
192.168.56.22   listify-app2
192.168.56.31   listify-db
```

### 5.2 ... et ses limites, qui sont le sujet du chapitre 9

Ce fichier doit être **répliqué et maintenu à la main sur N machines**. Ajoutez une machine (TP 6) : N fichiers à modifier. Oubliez-en un : une seule machine « voit » un ancien monde, et vous obtenez le pire type de panne, celle qui ne touche qu'un chemin. Vous vivrez exactement cet oubli au TP 6, il est prévu au scénario. La solution propre au-delà de quelques machines est un **DNS interne** (un dnsmasq sur une VM, une zone privée chez un cloud, le DNS de service de Kubernetes au S2...) : nous en ferons la démonstration en TD, mais le bloc assume `/etc/hosts` : sa maintenance douloureuse est un argument pédagogique pour la suite.

### 5.3 Conventions de nommage

Même discipline que pour les adresses : un nom encode le rôle (`listify-app1`, pas `serveur2`), en minuscules, avec un numéro d'instance pour les tiers multipliables. Les organisations y ajoutent l'environnement et le site (`app1.prod.par.example.internal`) ; retenez surtout la règle négative : **jamais de nom « mignon »** (planètes, personnages...) pour des machines interchangeables : on nomme ainsi ses animaux de compagnie, et le chapitre 9 vous dira tout le mal qu'il faut penser des serveurs-animaux de compagnie.

## Ce qu'il faut retenir

1. Le réseau privé inter-machines est un invariant d'architecture : VLAN au datacenter, VPC au cloud, host-only en TP. Carte NAT = Internet sortant ; carte host-only = trafic interne + administration ; mode pont interdit en salle.
2. Un plan d'adressage est une **convention documentée** : plages par zone, adresses statiques pour les serveurs, DHCP host-only désactivé. Le tableau du plan fait partie des livrables.
3. netplan : YAML déclaratif dans `/etc/netplan/`, permissions 600, **`netplan try`** en SSH, pas de gateway sur l'interface privée, indentation à l'espace.
4. Résolution interne : `/etc/hosts` identique partout à notre échelle ; ses oublis de synchronisation sont des pannes vicieuses et la première leçon de *drift* ; au-delà, DNS interne.
5. Les services se parlent **par noms**, configurés dans l'environnement, jamais par adresses en dur dans le code.

## Bibliographie du chapitre

### Sources primaires

- Oracle, *VirtualBox User Manual*, chapitre 6 « Virtual Networking » : le tableau des modes, avec les détails que ce chapitre résume. [virtualbox.org/manual/ch06.html](https://www.virtualbox.org/manual/ch06.html).
- Documentation netplan : [netplan.readthedocs.io](https://netplan.readthedocs.io/) (référence YAML et exemples) ; `man netplan-try`.
- RFC 1918, *Address Allocation for Private Internets*, 1996 : relire la section 3 avec les yeux de ce chapitre.
- Freedesktop, « Predictable Network Interface Names » : pourquoi `enp0s8` plutôt que `eth1`.

### Lectures recommandées

- Evi Nemeth et al., *UNIX and Linux System Administration Handbook*, 5ᵉ éd., chapitre 13 : sections sur l'adressage et la configuration réseau Linux.
- Ubuntu Server Documentation, section « Networking » : la référence du système utilisé en TP.

### Pour aller plus loin

- dnsmasq (documentation officielle) : le DNS+DHCP interne des petits parcs, montré en TD ; comparez son coût de mise en place à la maintenance de N fichiers hosts.
- AWS, « VPC and subnets » (documentation) : retrouvez chaque concept de ce chapitre (sous-réseau privé, plan d'adressage, résolution interne) dans le vocabulaire d'un cloud réel.
