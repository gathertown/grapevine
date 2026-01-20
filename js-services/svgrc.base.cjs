module.exports = {
  dimensions: false,
  memo: true,
  prettier: false,
  svgo: true,
  svgoConfig: {
    plugins: [
      {
        name: "removeAttrs",
        params: {
          attrs: ["style", "path[style]"],
        },
      },
      {
        name: "convertColors",
        params: {
          currentColor: true,
        },
      },
    ],
  },
  typescript: true,
}
