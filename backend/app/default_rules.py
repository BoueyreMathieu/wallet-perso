"""Règles de catégorisation par défaut (marques et libellés courants en France).

Format : (catégorie « Parent/Enfant », [motifs], priorité). Priorité basse = testée en premier.
Les motifs sont comparés en mots entiers, sans accents ni casse.
Tes propres règles (créées depuis l'appli) passent toujours avant celles-ci.

Ce fichier ne contient que des enseignes et libellés génériques : tes commerces habituels
sont appris dans ta base locale quand tu les catégorises, jamais ajoutés ici.
"""

DEFAULT_RULES: list[tuple[str, list[str], int]] = [
    # --- Cas particuliers, testés avant les règles générales ------------------------
    ("Transferts/Épargne / investissement", ["TRADE REPUBLIC", "BOURSORAMA BANQUE", "LINXEA", "YOMONI", "NALO", "RAMIFY", "BINANCE", "COINBASE"], 60),
    ("Revenus/Remboursements santé", ["CPAM", "AMELI", "CAISSE PRIMAIRE", "REMBOURSEMENT MUTUELLE"], 60),
    ("Revenus/Primes / épargne salariale", ["INTEREPARGNE", "EPARGNE SALARIALE", "AMUNDI ESR", "NATIXIS INTEREPARGNE", "INTERESSEMENT"], 60),
    ("Revenus/Aides / allocations", ["ALLOCATIONS FAMILIALES", "CAF ALLOCATIONS", "POLE EMPLOI", "FRANCE TRAVAIL", "PRIME D'ACTIVITE", "APL"], 60),
    ("Logement/Assurance habitation", ["ASSURANCE HABITATION", "MULTIRISQUE HABITATION"], 60),
    ("Transport/Assurance auto", ["ASSURANCE AUTOMOBILE", "ASSURANCE AUTO", "ASSURANCE 2 ROUES", "ASSURANCE MOTO"], 60),
    ("Assurances/Prévoyance / vie", ["PREVOYANCE", "ASSURANCE VIE", "ASSURANCE DECES"], 60),
    ("Assurances/Assurance emprunteur", ["ASSURANCE EMPRUNTEUR", "ASSURANCE PRET"], 60),
    ("Alimentation/Livraison", ["UBER EATS", "DELIVEROO", "JUST EAT"], 60),
    ("Banque & impôts/Frais bancaires", [
        "OFFRE COMPTE A COMPOSER", "COTISATION CARTE", "INTERETS DEBITEURS", "FRANCHISE INTERETS DEBITEURS",
        "FRAIS CARTE", "COMMISSION D'INTERVENTION", "FRAIS DE TENUE DE COMPTE", "AGIOS", "FRAIS BANCAIRES",
    ], 60),
    ("Banque & impôts/Retraits d'espèces", ["RETRAIT AU DISTRIBUTEUR", "RETRAIT DAB"], 60),
    ("Banque & impôts/Amendes", ["AMENDES.GOUV", "ANTAI", "AMENDE"], 65),
    ("Banque & impôts/Impôts", [
        "DIRECTION GENERALE DES FINANCES", "DGFIP", "IMPOT REVENUS", "IMPOTS.GOUV", "PRELEVEMENT A LA SOURCE",
        "TRESOR PUBLIC",
    ], 70),
    ("Logement/Taxes locales", ["TAXE FONCIERE", "TAXE D'HABITATION", "TAXE ORDURES"], 65),
    ("Famille & amis/Remboursements à des proches", ["WERO", "LYDIA", "PAYLIB"], 120),
    ("Shopping/Achats en ligne", ["PAYPAL", "AMAZON", "AMZN", "CDISCOUNT", "RAKUTEN", "ALIEXPRESS", "TEMU", "SHEIN", "VINTED", "LEBONCOIN", "WISH"], 90),

    # --- Alimentation ---------------------------------------------------------------
    ("Alimentation/Courses", [
        "INTERMARCHE", "CARREFOUR", "AUCHAN", "LECLERC", "LIDL", "ALDI", "CASINO", "MONOPRIX", "FRANPRIX",
        "VIVAL", "SPAR", "SUPER U", "HYPER U", "U EXPRESS", "SYSTEME U", "NETTO", "GRAND FRAIS", "PICARD",
        "BIOCOOP", "NATURALIA", "LA VIE CLAIRE", "COCCINELLE", "PROXI", "LEADER PRICE", "CORA",
        "EPICERIE", "PRIMEUR", "BOUCHERIE", "FROMAGERIE", "MARCHE",
    ], 100),
    ("Alimentation/Fast-food", [
        "MCDONALD'S", "MCDONALDS", "MC DONALD", "BURGER KING", "FIVE GUYS", "KFC", "SUBWAY", "QUICK",
        "DOMINO'S", "DOMINOS", "PIZZA HUT", "O'TACOS", "TACOS", "KEBAB", "BURGER",
    ], 95),
    ("Alimentation/Restaurants", ["PIZZA", "RESTAURANT", "RESTO", "BRASSERIE", "SUSHI", "CREPERIE", "BISTROT", "THAI", "TRATTORIA"], 100),
    ("Alimentation/Cantine / tickets resto", ["SODEXO", "ELIOR", "COMPASS", "EUREST", "RESTAURANT D'ENTREPRISE", "SWILE", "EDENRED", "TICKET RESTAURANT"], 90),
    ("Alimentation/Boulangerie / café", ["BOULANGERIE", "PATISSERIE", "STARBUCKS", "COLUMBUS CAFE", "BRIOCHE DOREE", "MARIE BLACHERE"], 100),
    ("Alimentation/Cave / alcool", ["NICOLAS", "V AND B", "V&B", "CAVISTE", "LA GRANDE CAVE"], 100),

    # --- Logement -------------------------------------------------------------------
    ("Logement/Loyer / crédit", ["LOYER", "REGIE", "RGIE", "FONCIA", "NEXITY", "CITYA", "ORPI", "CENTURY 21", "SQUARE HABITAT"], 100),
    ("Logement/Charges / syndic", ["SYNDIC", "CHARGES COPRO", "COPROPRIETE"], 95),
    ("Logement/Énergie", ["EDF", "ELECTRICITE DE FRANCE", "ENGIE", "TOTALENERGIES ELECTRICITE", "EKWATEUR", "OHM ENERGIE", "MINT ENERGIE", "GRDF"], 100),
    ("Logement/Eau", ["VEOLIA", "SUEZ", "SAUR", "EAU DE PARIS"], 100),
    ("Logement/Internet / téléphone", ["ORANGE", "SOSH", "SFR", "RED BY SFR", "BOUYGUES TELECOM", "B&YOU", "FREE MOBILE", "FREE TELECOM", "FREEBOX", "PRIXTEL", "NRJ MOBILE"], 100),
    ("Logement/Travaux / maison", ["LEROY MERLIN", "CASTORAMA", "BRICOMARCHE", "BRICO DEPOT", "MR BRICOLAGE", "WELDOM"], 100),
    ("Logement/Ameublement / déco", ["IKEA", "MAISONS DU MONDE", "CONFORAMA", "ALINEA", "HABITAT", "MAISON DU MONDE"], 100),
    ("Logement/Électroménager", ["DARTY ELECTROMENAGER", "ELECTRO DEPOT", "MIELE", "DYSON"], 95),

    # --- Transport ------------------------------------------------------------------
    ("Transport/Carburant", ["TOTALENERGIES", "TOTAL ACCESS", "ESSO", "SHELL", "AVIA", "STATION SERVICE", "BP"], 100),
    ("Transport/Transports en commun", ["RATP", "NAVIGO", "TISSEO", "STAR RENNES", "TAG GRENOBLE", "TBM", "FLIXBUS", "BLABLACAR BUS"], 100),
    ("Transport/Train / avion", ["SNCF", "OUIGO", "TRAINLINE", "TGV", "AIR FRANCE", "EASYJET", "RYANAIR", "TRANSAVIA", "VOLOTEA", "VUELING"], 100),
    ("Transport/Taxi / VTC", ["UBER", "BOLT", "HEETCH", "G7", "TAXI", "BLABLACAR"], 105),
    ("Transport/Vélo / trottinette", ["LIME", "DOTT", "VELIB", "CYCLEUROPE", "ALLTRICKS"], 100),
    ("Transport/Péage / parking", ["PEAGE", "APRR", "VINCI AUTOROUTES", "SANEF", "ASF", "INDIGO", "PARKING", "EFFIA", "Q-PARK", "ONEPARK"], 100),
    ("Transport/Entretien véhicule", ["NORAUTO", "FEU VERT", "MIDAS", "SPEEDY", "POINT S", "CONTROLE TECHNIQUE", "CARTE GRISE", "GARAGE"], 100),
    ("Transport/Location véhicule", ["EUROPCAR", "HERTZ", "SIXT", "GETAROUND", "UBEEQO", "ADA LOCATION"], 100),

    # --- Abonnements ----------------------------------------------------------------
    ("Abonnements/Streaming", ["NETFLIX", "DISNEY PLUS", "DISNEY+", "CANAL+", "CANAL PLUS", "PRIME VIDEO", "YOUTUBE PREMIUM", "CRUNCHYROLL", "MOLOTOV", "PARAMOUNT"], 80),
    ("Abonnements/Musique", ["SPOTIFY", "DEEZER", "APPLE MUSIC", "TIDAL", "QOBUZ", "YOUTUBE MUSIC"], 80),
    ("Abonnements/Jeux en ligne", ["XBOX GAME PASS", "GAME PASS", "PLAYSTATION PLUS", "PS PLUS", "NINTENDO ONLINE", "TWITCH"], 80),
    ("Abonnements/Logiciels / cloud", ["APPLE.COM/BILL", "ICLOUD", "GOOGLE ONE", "GOOGLE STORAGE", "MICROSOFT", "OFFICE 365", "ADOBE", "DROPBOX", "OPENAI", "CHATGPT", "ANTHROPIC", "CLAUDE.AI", "GITHUB", "NORDVPN", "PROTON", "REAL-DEBRID", "1PASSWORD", "BITWARDEN"], 80),
    ("Abonnements/Presse", ["LE MONDE", "LIBERATION", "MEDIAPART", "LE FIGARO", "CAFEYN"], 80),
    ("Abonnements/Salle de sport", ["BASIC FIT", "BASIC-FIT", "FITNESS PARK", "KEEP COOL", "ON AIR", "L'ORANGE BLEUE", "NEONESS", "CLUB MED GYM"], 80),

    # --- Loisirs --------------------------------------------------------------------
    ("Loisirs/Bars", ["BAR", "PUB", "CAFE", "BIERE", "BRASSERIE DU"], 105),
    ("Loisirs/Cinéma", ["PATHE", "CGR", "UGC", "MEGARAMA", "CINEMA", "KINEPOLIS", "MK2"], 100),
    ("Loisirs/Concerts / spectacles", ["TICKETMASTER", "FNAC SPECTACLES", "SEETICKETS", "DICE", "WEEZEVENT", "BILLETWEB", "FESTIVAL", "THEATRE"], 100),
    ("Loisirs/Sorties", ["CLUB", "PARC ASTERIX", "DISNEYLAND", "BOWLING", "LASER GAME", "ESCAPE GAME", "KARAOKE"], 106),
    ("Loisirs/Voyages", ["HOTEL", "AIRBNB", "BOOKING.COM", "IBIS", "CAMPANILE", "B&B HOTEL", "ABRITEL", "EXPEDIA", "CAMPING"], 100),
    ("Loisirs/Sport", ["DECATHLON", "INTERSPORT", "GO SPORT", "SPORT 2000", "SKIMIUM", "CLIMBING", "ESCALADE", "PISCINE"], 100),
    ("Loisirs/Jeux / culture", ["MICROMANIA", "STEAM", "STEAMGAMES", "PLAYSTATION", "SONY INTERACTIVE", "NINTENDO", "XBOX", "INSTANT GAMING", "EPIC GAMES", "FNAC", "HUMBLE", "GOG.COM"], 100),
    ("Loisirs/Livres / BD", ["GIBERT", "DECITRE", "LIBRAIRIE", "FURET DU NORD", "KINDLE"], 100),
    ("Loisirs/Hobbies / créatif", ["CULTURA", "GEMO LOISIRS", "ROUGIER", "CREAVEA"], 100),

    # --- Shopping -------------------------------------------------------------------
    ("Shopping/Vêtements", ["ZARA", "H&M", "H & M", "KIABI", "CELIO", "JULES", "UNIQLO", "PRIMARK", "BERSHKA", "PULL&BEAR", "ZALANDO", "ASOS", "LA HALLE"], 100),
    ("Shopping/Chaussures / accessoires", ["SNIPES", "COURIR", "FOOT LOCKER", "SAN MARINA", "ERAM", "BOCAGE", "SPARTOO"], 100),
    ("Shopping/High-tech", ["BOULANGER", "DARTY", "LDLC", "MATERIEL.NET", "APPLE STORE", "TOPACHAT", "GROSBILL", "BACK MARKET"], 100),
    ("Shopping/Maison", ["ACTION", "GIFI", "LA FOIR'FOUILLE", "HEMA", "CASA", "STOKOMANI", "NOZ"], 100),
    ("Shopping/Cadeaux", ["CAGNOTTE", "LYDIA CAGNOTTE", "SMARTBOX", "WONDERBOX"], 100),

    # --- Santé ----------------------------------------------------------------------
    ("Santé/Pharmacie", ["PHARMACIE", "PHARMA"], 100),
    ("Santé/Médecin", ["DOCTEUR", "MEDECIN", "CABINET MEDICAL", "DOCTOLIB", "CENTRE MEDICAL"], 100),
    ("Santé/Dentiste", ["DENTISTE", "DENTAIRE", "ORTHODONTISTE"], 100),
    ("Santé/Optique", ["OPTIC", "OPTICIEN", "AFFLELOU", "KRYS", "OPTICAL CENTER", "GRANDOPTICAL", "LISSAC"], 100),
    ("Santé/Paramédical", ["KINE", "KINESITHERAPEUTE", "OSTEOPATHE", "PODOLOGUE", "ORTHOPHONISTE", "INFIRMIER"], 100),
    ("Santé/Analyses / hôpital", ["LABORATOIRE", "BIOGROUP", "CERBALLIANCE", "HOPITAL", "CLINIQUE", "CHU"], 100),
    ("Santé/Mutuelle", ["MUTUELLE", "HARMONIE MUTUELLE", "MGEN", "ALAN", "MALAKOFF", "AG2R", "SWISSLIFE"], 100),

    # --- Beauté & soins -------------------------------------------------------------
    ("Beauté & soins/Coiffeur", ["COIFFURE", "COIFFEUR", "BARBIER", "BARBER", "SAINT ALGUE", "FRANCK PROVOST", "TCHIP"], 100),
    ("Beauté & soins/Cosmétiques", ["SEPHORA", "NOCIBE", "MARIONNAUD", "YVES ROCHER", "LUSH", "KIKO", "RITUALS"], 100),
    ("Beauté & soins/Soins / esthétique", ["ESTHETIQUE", "INSTITUT DE BEAUTE", "MANUCURE"], 100),

    # --- Autres dépenses ------------------------------------------------------------
    ("Éducation & formation/Formation", ["UDEMY", "COURSERA", "OPENCLASSROOMS", "CNED", "LINKEDIN LEARNING", "AUTO-ECOLE", "AUTO ECOLE"], 100),
    ("Éducation & formation/Fournitures", ["BUREAU VALLEE", "OFFICE DEPOT", "PAPETERIE"], 100),
    ("Animaux/Nourriture / accessoires", ["ANIMALIS", "MAXI ZOO", "TRUFFAUT", "JARDILAND", "ZOOPLUS", "ANIMALERIE"], 100),
    ("Animaux/Vétérinaire", ["VETERINAIRE", "CLINIQUE VETERINAIRE"], 100),
    ("Dons & associations/Dons", ["CROIX ROUGE", "MEDECINS SANS FRONTIERES", "RESTOS DU COEUR", "UNICEF", "WWF", "SECOURS POPULAIRE", "FONDATION"], 100),
    ("Dons & associations/Cotisations associatives", ["HELLOASSO", "ASSOCIATION", "ASSO", "ADHESION"], 110),
    ("Travail/Frais professionnels", ["NOTE DE FRAIS", "COWORKING", "WELCOME TO THE JUNGLE"], 100),

    # --- Revenus --------------------------------------------------------------------
    ("Revenus/Salaire", ["SALAIRE", "PAIE", "REMUNERATION"], 100),
    ("Revenus/Intérêts / dividendes", ["INTERETS CREDITEURS", "INTERETS ANNUELS", "DIVIDENDE"], 100),
    ("Revenus/Ventes", ["VINTED VENTE", "LEBONCOIN VENTE", "EBAY VENTE"], 85),
    ("Revenus/Autres revenus", ["URSSAF REMBOURSEMENT"], 110),
]
