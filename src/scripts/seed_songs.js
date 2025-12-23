const fs = require('fs');
const path = require('path');

const songsPath = path.join(__dirname, '../data/songs.json');

const newSongs = [
    // Pop / Top 40
    { title: "Shut Up and Dance", artist: "WALK THE MOON", genre: "Pop", duration: "3:19" },
    { title: "Uptown Funk", artist: "Mark Ronson ft. Bruno Mars", genre: "Funk/Pop", duration: "4:30" },
    { title: "Can't Stop the Feeling!", artist: "Justin Timberlake", genre: "Pop", duration: "3:56" },
    { title: "Shape of You", artist: "Ed Sheeran", genre: "Pop", duration: "3:53" },
    { title: "Levitating", artist: "Dua Lipa", genre: "Pop", duration: "3:23" },
    { title: "Bad Guy", artist: "Billie Eilish", genre: "Pop", duration: "3:14" },
    { title: "Watermelon Sugar", artist: "Harry Styles", genre: "Pop", duration: "2:54" },
    { title: "Stay", artist: "The Kid LAROI & Justin Bieber", genre: "Pop", duration: "2:21" },
    { title: "Industry Baby", artist: "Lil Nas X & Jack Harlow", genre: "Hip Hop", duration: "3:32" },
    { title: "Good 4 U", artist: "Olivia Rodrigo", genre: "Pop Rock", duration: "2:58" },
    { title: "Kiss Me More", artist: "Doja Cat ft. SZA", genre: "Pop", duration: "3:28" },
    { title: "About Damn Time", artist: "Lizzo", genre: "Pop/Funk", duration: "3:11" },
    { title: "Anti-Hero", artist: "Taylor Swift", genre: "Pop", duration: "3:20" },
    { title: "Unholy", artist: "Sam Smith & Kim Petras", genre: "Pop", duration: "2:36" },
    { title: "Cuff It", artist: "Beyoncé", genre: "R&B", duration: "3:45" },
    { title: "Flowers", artist: "Miley Cyrus", genre: "Pop", duration: "3:20" },
    { title: "Kill Bill", artist: "SZA", genre: "R&B", duration: "2:33" },
    { title: "Creepin'", artist: "Metro Boomin, The Weeknd, 21 Savage", genre: "R&B", duration: "3:41" },
    { title: "Last Night", artist: "Morgan Wallen", genre: "Country/Pop", duration: "2:43" },
    { title: "Fast Car", artist: "Luke Combs", genre: "Country", duration: "4:25" },
    { title: "Cruel Summer", artist: "Taylor Swift", genre: "Pop", duration: "2:58" },
    { title: "Vampire", artist: "Olivia Rodrigo", genre: "Pop Rock", duration: "3:39" },
    { title: "Paint The Town Red", artist: "Doja Cat", genre: "Hip Hop", duration: "3:51" },
    { title: "Dance The Night", artist: "Dua Lipa", genre: "Pop", duration: "2:56" },
    { title: "Espresso", artist: "Sabrina Carpenter", genre: "Pop", duration: "2:55" },

    // EDM / House / Club Classics
    { title: "Titanium", artist: "David Guetta ft. Sia", genre: "EDM", duration: "4:05" },
    { title: "Wake Me Up", artist: "Avicii", genre: "EDM", duration: "4:07" },
    { title: "Animals", artist: "Martin Garrix", genre: "EDM", duration: "2:56" },
    { title: "Clarity", artist: "Zedd ft. Foxes", genre: "EDM", duration: "4:31" },
    { title: "Don't You Worry Child", artist: "Swedish House Mafia", genre: "EDM", duration: "3:32" },
    { title: "This Is What You Came For", artist: "Calvin Harris ft. Rihanna", genre: "EDM", duration: "3:42" },
    { title: "Lean On", artist: "Major Lazer & DJ Snake", genre: "EDM", duration: "2:56" },
    { title: "Faded", artist: "Alan Walker", genre: "EDM", duration: "3:32" },
    { title: "Heroes (We Could Be)", artist: "Alesso ft. Tove Lo", genre: "EDM", duration: "3:30" },
    { title: "Middle", artist: "DJ Snake ft. Bipolar Sunshine", genre: "EDM", duration: "3:40" },
    { title: "The Middle", artist: "Zedd, Maren Morris, Grey", genre: "Pop/EDM", duration: "3:04" },
    { title: "Happier", artist: "Marshmello ft. Bastille", genre: "EDM", duration: "3:34" },
    { title: "Silence", artist: "Marshmello ft. Khalid", genre: "EDM", duration: "3:00" },
    { title: "Wolves", artist: "Selena Gomez & Marshmello", genre: "EDM", duration: "3:17" },
    { title: "One More Time", artist: "Daft Punk", genre: "House", duration: "5:20" },
    { title: "Around the World", artist: "Daft Punk", genre: "House", duration: "7:09" },
    { title: "Get Lucky", artist: "Daft Punk ft. Pharrell Williams", genre: "Funk/Pop", duration: "6:09" },
    { title: "Sandstorm", artist: "Darude", genre: "Trance", duration: "3:45" },
    { title: "Satisfaction", artist: "Benny Benassi", genre: "Techno", duration: "4:03" },
    { title: "Scary Monsters and Nice Sprites", artist: "Skrillex", genre: "Dubstep", duration: "4:03" },
    { title: "Bangarang", artist: "Skrillex", genre: "Dubstep", duration: "3:35" },
    { title: "Where Are Ü Now", artist: "Jack Ü ft. Justin Bieber", genre: "EDM", duration: "4:10" },

    // Hip Hop / Rap
    { title: "God's Plan", artist: "Drake", genre: "Hip Hop", duration: "3:18" },
    { title: "Nice For What", artist: "Drake", genre: "Hip Hop", duration: "3:30" },
    { title: "In My Feelings", artist: "Drake", genre: "Hip Hop", duration: "3:37" },
    { title: "One Dance", artist: "Drake ft. Wizkid & Kyla", genre: "Hip Hop/Dancehall", duration: "2:54" },
    { title: "Hotline Bling", artist: "Drake", genre: "Hip Hop", duration: "4:27" },
    { title: "SICKO MODE", artist: "Travis Scott", genre: "Hip Hop", duration: "5:12" },
    { title: "Goosebumps", artist: "Travis Scott", genre: "Hip Hop", duration: "4:03" },
    { title: "HUMBLE.", artist: "Kendrick Lamar", genre: "Hip Hop", duration: "2:57" },
    { title: "DNA.", artist: "Kendrick Lamar", genre: "Hip Hop", duration: "3:05" },
    { title: "Alright", artist: "Kendrick Lamar", genre: "Hip Hop", duration: "3:39" },
    { title: "N****s in Paris", artist: "Jay-Z & Kanye West", genre: "Hip Hop", duration: "3:39" },
    { title: "Stronger", artist: "Kanye West", genre: "Hip Hop", duration: "5:11" },
    { title: "Gold Digger", artist: "Kanye West ft. Jamie Foxx", genre: "Hip Hop", duration: "3:28" },
    { title: "Bodak Yellow", artist: "Cardi B", genre: "Hip Hop", duration: "3:43" },
    { title: "I Like It", artist: "Cardi B, Bad Bunny & J Balvin", genre: "Hip Hop/Latin", duration: "4:13" },
    { title: "WAP", artist: "Cardi B ft. Megan Thee Stallion", genre: "Hip Hop", duration: "3:07" },
    { title: "Savage (Remix)", artist: "Megan Thee Stallion ft. Beyoncé", genre: "Hip Hop", duration: "4:02" },
    { title: "Truth Hurts", artist: "Lizzo", genre: "Pop/Hip Hop", duration: "2:53" },
    { title: "Old Town Road", artist: "Lil Nas X ft. Billy Ray Cyrus", genre: "Country Rap", duration: "2:37" },
    { title: "Rockstar", artist: "Post Malone ft. 21 Savage", genre: "Hip Hop", duration: "3:38" },
    { title: "Circles", artist: "Post Malone", genre: "Pop Rock", duration: "3:35" },
    { title: "Sunflower", artist: "Post Malone & Swae Lee", genre: "Pop/Hip Hop", duration: "2:38" },
    { title: "Congratulations", artist: "Post Malone ft. Quavo", genre: "Hip Hop", duration: "3:40" },
    { title: "Black Beatles", artist: "Rae Sremmurd ft. Gucci Mane", genre: "Hip Hop", duration: "4:51" },
    { title: "Bad and Boujee", artist: "Migos ft. Lil Uzi Vert", genre: "Hip Hop", duration: "5:43" },
    { title: "Mask Off", artist: "Future", genre: "Hip Hop", duration: "3:24" },
    { title: "XO Tour Llif3", artist: "Lil Uzi Vert", genre: "Hip Hop", duration: "3:02" },
    { title: "Lucid Dreams", artist: "Juice WRLD", genre: "Hip Hop", duration: "3:59" },
    { title: "Mo Bamba", artist: "Sheck Wes", genre: "Hip Hop", duration: "3:01" },

    // Rock / Alternative Anthems
    { title: "Smells Like Teen Spirit", artist: "Nirvana", genre: "Rock", duration: "5:01" },
    { title: "Livin' on a Prayer", artist: "Bon Jovi", genre: "Rock", duration: "4:09" },
    { title: "Sweet Child O' Mine", artist: "Guns N' Roses", genre: "Rock", duration: "5:56" },
    { title: "Bohemian Rhapsody", artist: "Queen", genre: "Rock", duration: "5:55" },
    { title: "We Will Rock You", artist: "Queen", genre: "Rock", duration: "2:01" },
    { title: "Another One Bites the Dust", artist: "Queen", genre: "Rock", duration: "3:35" },
    { title: "Don't Stop Me Now", artist: "Queen", genre: "Rock", duration: "3:29" },
    { title: "Eye of the Tiger", artist: "Survivor", genre: "Rock", duration: "4:04" },
    { title: "Enter Sandman", artist: "Metallica", genre: "Metal", duration: "5:31" },
    { title: "Numb", artist: "Linkin Park", genre: "Rock", duration: "3:07" },
    { title: "In the End", artist: "Linkin Park", genre: "Rock", duration: "3:36" },
    { title: "Bring Me To Life", artist: "Evanescence", genre: "Rock", duration: "3:57" },
    { title: "Teenage Dirtbag", artist: "Wheatus", genre: "Rock", duration: "4:07" },
    { title: "Wonderwall", artist: "Oasis", genre: "Britpop", duration: "4:18" },
    { title: "Champagne Supernova", artist: "Oasis", genre: "Britpop", duration: "7:28" },
    { title: "Song 2", artist: "Blur", genre: "Britpop", duration: "2:01" },
    { title: "Seven Nation Army", artist: "The White Stripes", genre: "Rock", duration: "3:51" },
    { title: "The Middle", artist: "Jimmy Eat World", genre: "Pop Punk", duration: "2:45" },
    { title: "All The Small Things", artist: "Blink-182", genre: "Pop Punk", duration: "2:47" },
    { title: "Sugar, We're Goin Down", artist: "Fall Out Boy", genre: "Pop Punk", duration: "3:49" },
    { title: "I Write Sins Not Tragedies", artist: "Panic! At The Disco", genre: "Pop Punk", duration: "3:07" },
    { title: "Welcome to the Black Parade", artist: "My Chemical Romance", genre: "Rock", duration: "5:11" },
    { title: "Misery Business", artist: "Paramore", genre: "Pop Punk", duration: "3:31" },
    { title: "Sex on Fire", artist: "Kings of Leon", genre: "Rock", duration: "3:28" },
    { title: "Use Somebody", artist: "Kings of Leon", genre: "Rock", duration: "3:50" },

    // Latin / Reggaeton
    { title: "Bailando", artist: "Enrique Iglesias", genre: "Latin", duration: "4:03" },
    { title: "Mia", artist: "Bad Bunny ft. Drake", genre: "Latin", duration: "3:30" },
    { title: "Dakiti", artist: "Bad Bunny & Jhay Cortez", genre: "Reggaeton", duration: "3:25" },
    { title: "Yonaguni", artist: "Bad Bunny", genre: "Reggaeton", duration: "3:26" },
    { title: "Callaita", artist: "Bad Bunny & Tainy", genre: "Reggaeton", duration: "4:10" },
    { title: "Me Porto Bonito", artist: "Bad Bunny & Chencho Corleone", genre: "Reggaeton", duration: "2:58" },
    { title: "Moscow Mule", artist: "Bad Bunny", genre: "Reggaeton", duration: "4:05" },
    { title: "Provenza", artist: "Karol G", genre: "Reggaeton", duration: "3:30" },
    { title: "TQG", artist: "Karol G & Shakira", genre: "Reggaeton", duration: "3:18" },
    { title: "Mamiii", artist: "Becky G & Karol G", genre: "Reggaeton", duration: "3:47" },
    { title: "Hips Don't Lie", artist: "Shakira ft. Wyclef Jean", genre: "Latin", duration: "3:38" },
    { title: "Waka Waka", artist: "Shakira", genre: "Latin", duration: "3:22" },
    { title: "Vivir Mi Vida", artist: "Marc Anthony", genre: "Salsa", duration: "4:11" },
    { title: "Suavemente", artist: "Elvis Crespo", genre: "Merengue", duration: "4:27" },

    // Throwback / Wedding Favorites
    { title: "September", artist: "Earth, Wind & Fire", genre: "Disco", duration: "3:35" },
    { title: "Boogie Wonderland", artist: "Earth, Wind & Fire", genre: "Disco", duration: "4:48" },
    { title: "Dancing Queen", artist: "ABBA", genre: "Pop", duration: "3:50" },
    { title: "Mamma Mia", artist: "ABBA", genre: "Pop", duration: "3:32" },
    { title: "Stayin' Alive", artist: "Bee Gees", genre: "Disco", duration: "4:45" },
    { title: "I Will Survive", artist: "Gloria Gaynor", genre: "Disco", duration: "3:17" },
    { title: "Y.M.C.A.", artist: "Village People", genre: "Disco", duration: "4:47" },
    { title: "Billie Jean", artist: "Michael Jackson", genre: "Pop", duration: "4:54" },
    { title: "Thriller", artist: "Michael Jackson", genre: "Pop", duration: "5:57" },
    { title: "Beat It", artist: "Michael Jackson", genre: "Rock", duration: "4:18" },
    { title: "Wannabe", artist: "Spice Girls", genre: "Pop", duration: "2:52" },
    { title: "No Scrubs", artist: "TLC", genre: "R&B", duration: "3:34" },
    { title: "Toxic", artist: "Britney Spears", genre: "Pop", duration: "3:18" },
    { title: "Baby One More Time", artist: "Britney Spears", genre: "Pop", duration: "3:30" },
    { title: "Hey Ya!", artist: "OutKast", genre: "Hip Hop", duration: "3:55" },
    { title: "Crazy in Love", artist: "Beyoncé ft. Jay-Z", genre: "R&B", duration: "3:56" },
    { title: "Single Ladies", artist: "Beyoncé", genre: "R&B", duration: "3:13" },
    { title: "Umbrella", artist: "Rihanna ft. Jay-Z", genre: "Pop", duration: "4:35" },
];

function seed() {
    let existingSongs = [];
    try {
        const data = fs.readFileSync(songsPath, 'utf8');
        existingSongs = JSON.parse(data);
    } catch (e) { }

    // Avoid duplicates by title
    const existingTitles = new Set(existingSongs.map(s => s.title.toLowerCase()));

    const songsToAdd = newSongs.filter(s => !existingTitles.has(s.title.toLowerCase()));

    const finalSongs = [
        ...existingSongs,
        ...songsToAdd.map((s, i) => ({
            ...s,
            id: (existingSongs.length + i + 1).toString()
        }))
    ];

    fs.writeFileSync(songsPath, JSON.stringify(finalSongs, null, 2));
    console.log(`Added ${songsToAdd.length} new songs. Total: ${finalSongs.length}`);
}

seed();
