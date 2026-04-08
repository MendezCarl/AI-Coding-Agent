async function sleep(seconds) {
  const ms = Math.max(0, Number(seconds || 0)) * 1000;
  // eslint-disable-next-line no-promise-executor-return
  await new Promise((resolve) => setTimeout(resolve, ms));
}

module.exports = { sleep };

