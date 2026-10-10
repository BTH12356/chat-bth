"use strict";

fetch("project-config.json")
  .then((response) => {
    if (!response.ok) throw new Error(`Configuration request failed: ${response.status}`);
    return response.json();
  })
  .then((config) => {
    document.getElementById("build-status").textContent = `Frozen spec: ${config.frozen_spec_id}`;
  })
  .catch((error) => {
    document.getElementById("build-status").textContent = error.message;
  });
