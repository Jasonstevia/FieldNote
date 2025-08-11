# How to Get Started with a Wasm 'Hello World'

WebAssembly (Wasm) is rapidly changing the landscape of web development and beyond. It's a binary instruction format that acts as a compilation target for high-level languages like C, C++, and Rust, enabling near-native performance for applications running in the browser. If you're looking to **learn wasm**, there's no better way to start than with the classic "Hello, World!" example.

This hands-on **webassembly tutorial** will guide you through compiling a simple C program into a Wasm module and running it in your web browser. It's the perfect first step for **getting started with wasm**. Let's dive in.

## What You'll Need

Before we begin, make sure you have a few basic tools ready:

1.  A text editor (like VS Code, Sublime Text, or Vim).
2.  A modern web browser (Chrome, Firefox, Safari, or Edge).
3.  The **Emscripten SDK**, a complete open-source toolchain for compiling to WebAssembly.

Emscripten is the magic ingredient here. It not only compiles your C/C++ code into a `.wasm` file but also generates the necessary JavaScript "glue" code to load and run it on the web.

## Step 1: Set Up the Emscripten Environment

First, we need to install the Emscripten SDK. The most straightforward way is by cloning its repository from GitHub. Open your terminal and run the following commands:

```bash
# Clone the Emscripten SDK repository
git clone https://github.com/emscripten-core/emsdk.git

# Navigate into the directory
cd emsdk
```

Next, we'll install and activate the latest version of the SDK.

```bash
# Download and install the latest SDK tools
./emsdk install latest

# Activate the latest SDK
./emsdk activate latest
```

Finally, to use `emcc` (the Emscripten compiler) directly from your command line, you need to add its location to your current shell's environment.

```bash
# Set up the environment variables for the current terminal session
source ./emsdk_env.sh
```
**Note:** You'll need to run this `source` command every time you open a new terminal session to work with Emscripten.

## Step 2: Write Your 'Hello World' C Code

Now for the fun part. Create a new file named `hello.c` in a new project directory (outside the `emsdk` folder). Open it in your text editor and add the following C code:

```c
#include <stdio.h>

int main() {
    printf("Hello, World from Wasm!\n");
    return 0;
}
```

This is a standard C program. You might wonder how `printf` works in a browser. Emscripten is smart; by default, it pipes the `stdout` from your C code to the browser's JavaScript console using `console.log()`.

## Step 3: Compile C to a **Hello World Wasm** Module

With your `hello.c` file saved, navigate to its directory in your terminal (the one with the activated Emscripten environment). Run the following command to compile it:

```bash
emcc hello.c -o hello.html
```

Let's break down this command:
*   `emcc`: This is the Emscripten compiler command.
*   `hello.c`: This is our input source file.
*   `-o hello.html`: This is the crucial part for beginners. Instead of just creating a `.wasm` file, this flag tells Emscripten to generate an HTML host page (`hello.html`), the JavaScript glue code (`hello.js`), and the WebAssembly module (`hello.wasm`). It packages everything you need to run the code immediately.

After the command finishes, you'll see three new files in your directory: `hello.html`, `hello.js`, and `hello.wasm`.

## Step 4: Run Your WebAssembly Application

You can't just open the `hello.html` file directly in your browser from your local file system due to browser security restrictions (CORS policies). You need to serve it from a local web server.

If you have Python 3 installed, this is incredibly simple. From your project directory, run:

```bash
python -m http.server
```

This will start a web server, typically on port 8000. Now, open your web browser and navigate to `http://localhost:8000/hello.html`.

You won't see anything on the page itself. The magic is in the developer console. Open your browser's developer tools (usually by pressing F12 or Ctrl+Shift+I / Cmd+Opt+I) and click on the "Console" tab. You should see the message:

```
Hello, World from Wasm!
```

Congratulations! You've just successfully completed your first **hello world wasm** project.

## What's Next?

You've taken a massive first step on your journey to **learn wasm**. You compiled C code into a high-performance binary format and ran it seamlessly in a web browser.

From here, the possibilities are endless. You can start exploring:
*   **Passing data** between JavaScript and WebAssembly.
*   Compiling other languages like **Rust** or **Go** to Wasm.
*   Rendering graphics using WebGL from your Wasm module.

To continue your learning, be sure to check out more expert guides and tutorials right here on [fieldnote.wasmer.app](https://fieldnote.wasmer.app/). We're dedicated to exploring the power and potential of WebAssembly.