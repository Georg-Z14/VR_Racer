document.addEventListener("DOMContentLoaded", () => {
  const data = [
    { rank: "🥇", name: "Noah Müller", track: "Neon City Sprint", time: "02:13.24", car: "Cyber GT" },
    { rank: "🥈", name: "Lara Fischer", track: "Pro-League Cup", time: "02:16.02", car: "Tempest XR" },
    { rank: "🥉", name: "Finn Reuter", track: "Midnight Circuit", time: "02:18.11", car: "Vortex 5" },
    { rank: "4️⃣", name: "Jonas Wolf", track: "Desert Dash", time: "02:20.08", car: "Blaze 9R" },
    { rank: "5️⃣", name: "Alina Brandt", track: "Aqua Dome", time: "02:22.44", car: "Hydra Evo" },
  ];

  const table = document.getElementById("leaderboard-body");
  table.innerHTML = data.map(r => `
    <tr>
      <td>${r.rank}</td>
      <td>${r.name}</td>
      <td>${r.track}</td>
      <td>${r.time}</td>
      <td>${r.car}</td>
    </tr>
  `).join("");
});